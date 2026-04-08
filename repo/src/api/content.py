"""Content governance and moderation endpoints - plan section 6.5."""

from datetime import datetime, timezone, timedelta

from flask import Blueprint, request, g
from sqlalchemy import func

import hashlib
import json
import re

from src.models.base import db
from src.models.models import (
    ContentItem, ContentRating, ContentComment, ContentFavorite,
    ContentDownload, ModerationCase, AuditEvent, User, Membership,
)
from src.models.enums import (
    ContentQualityState, ContentType, ModerationAction,
    AuditEventType, RoleType,
)
from src.security.auth_middleware import require_auth, require_role, require_permission
from src.utils.responses import success_response, error_response, list_response
from src.utils.pagination import paginate_query
from src.utils.validators import validate_required
from src.logging import logger
from src.config import config


content_bp = Blueprint("content", __name__, url_prefix="")


# ──────────────────────────────────────────
# Helper functions
# ──────────────────────────────────────────

def _normalize_fingerprint(title: str, body: str) -> str:
    """Generate a duplicate-detection fingerprint hash.

    Concatenates title and body, lowercases, strips extra whitespace,
    removes all non-alphanumeric characters except spaces, and returns
    the SHA-256 hex digest.
    """
    combined = (title or "") + " " + (body or "")
    combined = combined.lower()
    combined = combined.strip()
    combined = re.sub(r"[^a-z0-9 ]", "", combined)
    combined = re.sub(r"\s+", " ", combined).strip()
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()


def _serialize_content_item(item: ContentItem) -> dict:
    """Serialize a ContentItem model to dict."""
    return {
        "id": item.id,
        "organization_id": item.organization_id,
        "creator_id": item.creator_id,
        "title": item.title,
        "body": item.body,
        "content_type": item.content_type,
        "quality_state": item.quality_state,
        "fingerprint_hash": item.fingerprint_hash,
        "avg_rating": item.avg_rating,
        "rating_count": item.rating_count,
        "view_count": item.view_count,
        "download_count": item.download_count,
        "is_active": item.is_active,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


def _serialize_rating(rating: ContentRating) -> dict:
    """Serialize a ContentRating model to dict."""
    return {
        "id": rating.id,
        "user_id": rating.user_id,
        "content_id": rating.content_id,
        "score": rating.score,
        "created_at": rating.created_at.isoformat() if rating.created_at else None,
        "updated_at": rating.updated_at.isoformat() if rating.updated_at else None,
    }


def _serialize_comment(comment: ContentComment) -> dict:
    """Serialize a ContentComment model to dict."""
    return {
        "id": comment.id,
        "user_id": comment.user_id,
        "content_id": comment.content_id,
        "body": comment.body,
        "is_visible": comment.is_visible,
        "created_at": comment.created_at.isoformat() if comment.created_at else None,
    }


def _serialize_favorite(fav: ContentFavorite) -> dict:
    """Serialize a ContentFavorite model to dict."""
    return {
        "id": fav.id,
        "user_id": fav.user_id,
        "content_id": fav.content_id,
        "created_at": fav.created_at.isoformat() if fav.created_at else None,
    }


def _serialize_download(dl: ContentDownload) -> dict:
    """Serialize a ContentDownload model to dict."""
    return {
        "id": dl.id,
        "user_id": dl.user_id,
        "content_id": dl.content_id,
        "created_at": dl.created_at.isoformat() if dl.created_at else None,
    }


def _serialize_moderation_case(case: ModerationCase) -> dict:
    """Serialize a ModerationCase model to dict."""
    return {
        "id": case.id,
        "content_id": case.content_id,
        "reporter_id": case.reporter_id,
        "reviewer_id": case.reviewer_id,
        "action": case.action,
        "reason": case.reason,
        "decision_notes": case.decision_notes,
        "appeal_notes": case.appeal_notes,
        "appeal_decision_notes": case.appeal_decision_notes,
        "appealed_at": case.appealed_at.isoformat() if case.appealed_at else None,
        "decided_at": case.decided_at.isoformat() if case.decided_at else None,
        "created_at": case.created_at.isoformat() if case.created_at else None,
        "updated_at": case.updated_at.isoformat() if case.updated_at else None,
    }


def _is_platform_admin() -> bool:
    """Check if the current user is a platform admin."""
    return getattr(g.current_user, "role", None) == RoleType.PLATFORM_ADMIN.value


def _has_reviewer_role() -> bool:
    """Check if the current user has a reviewer-level permission."""
    permissions = getattr(g.current_user, "permissions", []) or []
    return "moderation:review" in permissions


# ──────────────────────────────────────────
# POST /content
# ──────────────────────────────────────────
@content_bp.route("/content", methods=["POST"])
@require_auth
def create_content():
    try:
        current = g.current_user
        data = request.get_json(silent=True) or {}

        errors = validate_required(data, ["title", "organization_id"])
        if errors:
            return error_response(
                "VALIDATION_ERROR", "Missing required fields",
                details=errors, status_code=400,
            )

        title = data["title"]
        body = data.get("body", "")
        content_type = data.get("content_type", ContentType.ARTICLE.value)
        organization_id = data["organization_id"]

        # Validate content_type
        valid_content_types = [ct.value for ct in ContentType]
        if content_type not in valid_content_types:
            return error_response(
                "VALIDATION_ERROR",
                f"content_type must be one of: {', '.join(valid_content_types)}",
                status_code=400,
            )

        # Compute duplicate fingerprint
        fingerprint_hash = _normalize_fingerprint(title, body)

        # Default quality state
        quality_state = ContentQualityState.ACTIVE.value

        # Duplicate detection: check for ACTIVE content in same org with same fingerprint
        existing_dup = ContentItem.query.filter_by(
            organization_id=organization_id,
            fingerprint_hash=fingerprint_hash,
            quality_state=ContentQualityState.ACTIVE.value,
        ).first()

        if existing_dup:
            quality_state = ContentQualityState.DUPLICATE_DEMOTED.value

        content_item = ContentItem(
            organization_id=organization_id,
            creator_id=current.user_id,
            title=title,
            body=body,
            content_type=content_type,
            quality_state=quality_state,
            fingerprint_hash=fingerprint_hash,
        )
        db.session.add(content_item)
        db.session.flush()

        # Audit event
        audit = AuditEvent(
            event_type=AuditEventType.CONTENT_CREATED.value,
            actor_id=current.user_id,
            actor_ip=request.remote_addr,
            target_type="ContentItem",
            target_id=content_item.id,
            organization_id=organization_id,
            after_state=json.dumps(_serialize_content_item(content_item)),
        )
        db.session.add(audit)
        db.session.commit()

        logger.info(
            "content", "create",
            f"Content created: id={content_item.id} org={organization_id} "
            f"quality_state={quality_state}",
        )

        return success_response(_serialize_content_item(content_item), status_code=201)

    except Exception as exc:
        db.session.rollback()
        logger.error("content", "create", f"Unexpected error: {exc}")
        return error_response("INTERNAL_ERROR", "An unexpected error occurred", status_code=500)


# ──────────────────────────────────────────
# GET /content
# ──────────────────────────────────────────
@content_bp.route("/content", methods=["GET"])
@require_auth
def list_content():
    try:
        current = g.current_user
        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", config.DEFAULT_PAGE_SIZE, type=int)
        sort_by = request.args.get("sort_by", "created_at")
        sort_order = request.args.get("sort_order", "desc")

        # Filters
        content_type_filter = request.args.get("content_type")
        quality_state_filter = request.args.get("quality_state")
        creator_id_filter = request.args.get("creator_id")
        search = request.args.get("search")
        organization_id = request.args.get("organization_id", current.organization_id)

        query = ContentItem.query

        # Org scope
        if organization_id:
            query = query.filter(ContentItem.organization_id == organization_id)

        # Exclude SUPPRESSED content for non-admin/non-reviewer unless they own it
        if not _is_platform_admin() and not _has_reviewer_role():
            query = query.filter(
                db.or_(
                    ContentItem.quality_state != ContentQualityState.SUPPRESSED.value,
                    ContentItem.creator_id == current.user_id,
                )
            )

        # Apply filters
        if content_type_filter:
            query = query.filter(ContentItem.content_type == content_type_filter)
        if quality_state_filter:
            query = query.filter(ContentItem.quality_state == quality_state_filter)
        if creator_id_filter:
            query = query.filter(ContentItem.creator_id == creator_id_filter)
        if search:
            query = query.filter(ContentItem.title.ilike(f"%{search}%"))

        # Sorting
        if sort_by == "avg_rating":
            sort_column = ContentItem.avg_rating
        elif sort_by == "view_count":
            sort_column = ContentItem.view_count
        else:
            sort_column = ContentItem.created_at

        if sort_order == "asc":
            query = query.order_by(sort_column.asc())
        else:
            query = query.order_by(sort_column.desc())

        result = paginate_query(query, page, per_page)

        # Increment view_count for returned items
        item_ids = [item.id for item in result["items"]]
        if item_ids:
            ContentItem.query.filter(ContentItem.id.in_(item_ids)).update(
                {ContentItem.view_count: ContentItem.view_count + 1},
                synchronize_session=False,
            )
            db.session.commit()

        items = [_serialize_content_item(item) for item in result["items"]]
        return list_response(items, result["pagination"])

    except Exception as exc:
        db.session.rollback()
        logger.error("content", "list", f"Unexpected error: {exc}")
        return error_response("INTERNAL_ERROR", "An unexpected error occurred", status_code=500)


# ──────────────────────────────────────────
# POST /content/<id>/ratings
# ──────────────────────────────────────────
@content_bp.route("/content/<content_id>/ratings", methods=["POST"])
@require_auth
def rate_content(content_id):
    try:
        current = g.current_user
        data = request.get_json(silent=True) or {}

        errors = validate_required(data, ["score"])
        if errors:
            return error_response(
                "VALIDATION_ERROR", "Missing required fields",
                details=errors, status_code=400,
            )

        score = data["score"]
        if not isinstance(score, int) or score < 1 or score > 5:
            return error_response(
                "VALIDATION_ERROR", "score must be an integer between 1 and 5",
                status_code=400,
            )

        # Find content item
        content_item = ContentItem.query.get(content_id)
        if content_item is None:
            return error_response("NOT_FOUND", "Content item not found", status_code=404)

        # Verify org scope
        if not _is_platform_admin():
            if content_item.organization_id != current.organization_id:
                membership = Membership.query.filter_by(
                    user_id=current.user_id,
                    organization_id=content_item.organization_id,
                    is_active=True,
                ).first()
                if not membership:
                    return error_response(
                        "FORBIDDEN",
                        "You do not have access to this content item",
                        status_code=403,
                    )

        # Upsert rating (unique user_id + content_id)
        existing_rating = ContentRating.query.filter_by(
            user_id=current.user_id,
            content_id=content_id,
        ).first()

        if existing_rating:
            existing_rating.score = score
            existing_rating.updated_at = datetime.now(timezone.utc)
            rating = existing_rating
            is_new = False
        else:
            rating = ContentRating(
                user_id=current.user_id,
                content_id=content_id,
                score=score,
            )
            db.session.add(rating)
            is_new = True

        db.session.flush()

        # Recalculate avg_rating and rating_count on ContentItem
        agg = db.session.query(
            func.count(ContentRating.id),
            func.avg(ContentRating.score),
        ).filter(ContentRating.content_id == content_id).one()

        content_item.rating_count = agg[0] or 0
        content_item.avg_rating = round(float(agg[1] or 0), 2)

        # Check rating demotion
        demoted = False
        if (
            content_item.rating_count >= config.RATING_DEMOTION_MIN_COUNT
            and content_item.avg_rating < config.RATING_DEMOTION_THRESHOLD
            and content_item.quality_state == ContentQualityState.ACTIVE.value
        ):
            before_state = content_item.quality_state
            content_item.quality_state = ContentQualityState.RATING_DEMOTED.value
            demoted = True

            audit = AuditEvent(
                event_type=AuditEventType.CONTENT_DEMOTED.value,
                actor_id=current.user_id,
                actor_ip=request.remote_addr,
                target_type="ContentItem",
                target_id=content_item.id,
                organization_id=content_item.organization_id,
                before_state=json.dumps({"quality_state": before_state}),
                after_state=json.dumps({
                    "quality_state": content_item.quality_state,
                    "avg_rating": content_item.avg_rating,
                    "rating_count": content_item.rating_count,
                }),
            )
            db.session.add(audit)

        db.session.commit()

        logger.info(
            "content", "rate",
            f"Rating {'updated' if not is_new else 'created'}: "
            f"content_id={content_id} user={current.user_id} score={score}"
            f"{' (DEMOTED)' if demoted else ''}",
        )

        return success_response(
            _serialize_rating(rating),
            status_code=200 if not is_new else 201,
        )

    except Exception as exc:
        db.session.rollback()
        logger.error("content", "rate", f"Unexpected error: {exc}")
        return error_response("INTERNAL_ERROR", "An unexpected error occurred", status_code=500)


# ──────────────────────────────────────────
# POST /content/<id>/comments
# ──────────────────────────────────────────
@content_bp.route("/content/<content_id>/comments", methods=["POST"])
@require_auth
def create_comment(content_id):
    try:
        current = g.current_user
        data = request.get_json(silent=True) or {}

        errors = validate_required(data, ["body"])
        if errors:
            return error_response(
                "VALIDATION_ERROR", "Missing required fields",
                details=errors, status_code=400,
            )

        body = data["body"]

        # Find content item
        content_item = ContentItem.query.get(content_id)
        if content_item is None:
            return error_response("NOT_FOUND", "Content item not found", status_code=404)

        comment = ContentComment(
            user_id=current.user_id,
            content_id=content_id,
            body=body,
        )
        db.session.add(comment)
        db.session.commit()

        logger.info(
            "content", "comment",
            f"Comment created: id={comment.id} content_id={content_id} user={current.user_id}",
        )

        return success_response(_serialize_comment(comment), status_code=201)

    except Exception as exc:
        db.session.rollback()
        logger.error("content", "comment", f"Unexpected error: {exc}")
        return error_response("INTERNAL_ERROR", "An unexpected error occurred", status_code=500)


# ──────────────────────────────────────────
# POST /content/<id>/favorite
# ──────────────────────────────────────────
@content_bp.route("/content/<content_id>/favorite", methods=["POST"])
@require_auth
def add_favorite(content_id):
    try:
        current = g.current_user

        # Find content item
        content_item = ContentItem.query.get(content_id)
        if content_item is None:
            return error_response("NOT_FOUND", "Content item not found", status_code=404)

        # Idempotent: check for existing favorite
        existing = ContentFavorite.query.filter_by(
            user_id=current.user_id,
            content_id=content_id,
        ).first()

        if existing:
            logger.info(
                "content", "favorite",
                f"Favorite already exists: content_id={content_id} user={current.user_id}",
            )
            return success_response(_serialize_favorite(existing), status_code=200)

        favorite = ContentFavorite(
            user_id=current.user_id,
            content_id=content_id,
        )
        db.session.add(favorite)
        db.session.commit()

        logger.info(
            "content", "favorite",
            f"Favorite created: content_id={content_id} user={current.user_id}",
        )

        return success_response(_serialize_favorite(favorite), status_code=201)

    except Exception as exc:
        db.session.rollback()
        logger.error("content", "favorite", f"Unexpected error: {exc}")
        return error_response("INTERNAL_ERROR", "An unexpected error occurred", status_code=500)


# ──────────────────────────────────────────
# DELETE /content/<id>/favorite
# ──────────────────────────────────────────
@content_bp.route("/content/<content_id>/favorite", methods=["DELETE"])
@require_auth
def remove_favorite(content_id):
    try:
        current = g.current_user

        favorite = ContentFavorite.query.filter_by(
            user_id=current.user_id,
            content_id=content_id,
        ).first()

        if not favorite:
            return error_response("NOT_FOUND", "Favorite not found", status_code=404)

        db.session.delete(favorite)
        db.session.commit()

        logger.info(
            "content", "unfavorite",
            f"Favorite removed: content_id={content_id} user={current.user_id}",
        )

        return "", 204

    except Exception as exc:
        db.session.rollback()
        logger.error("content", "unfavorite", f"Unexpected error: {exc}")
        return error_response("INTERNAL_ERROR", "An unexpected error occurred", status_code=500)


# ──────────────────────────────────────────
# POST /content/<id>/download
# ──────────────────────────────────────────
@content_bp.route("/content/<content_id>/download", methods=["POST"])
@require_auth
def download_content(content_id):
    try:
        current = g.current_user

        # Find content item
        content_item = ContentItem.query.get(content_id)
        if content_item is None:
            return error_response("NOT_FOUND", "Content item not found", status_code=404)

        # Create download record
        download = ContentDownload(
            user_id=current.user_id,
            content_id=content_id,
        )
        db.session.add(download)

        # Increment download_count
        content_item.download_count = content_item.download_count + 1
        db.session.commit()

        logger.info(
            "content", "download",
            f"Download recorded: content_id={content_id} user={current.user_id} "
            f"total_downloads={content_item.download_count}",
        )

        return success_response({
            "download": _serialize_download(download),
            "download_count": content_item.download_count,
        }, status_code=200)

    except Exception as exc:
        db.session.rollback()
        logger.error("content", "download", f"Unexpected error: {exc}")
        return error_response("INTERNAL_ERROR", "An unexpected error occurred", status_code=500)


# ──────────────────────────────────────────
# POST /content/<id>/report
# ──────────────────────────────────────────
@content_bp.route("/content/<content_id>/report", methods=["POST"])
@require_auth
def report_content(content_id):
    try:
        current = g.current_user
        data = request.get_json(silent=True) or {}

        errors = validate_required(data, ["reason"])
        if errors:
            return error_response(
                "VALIDATION_ERROR", "Missing required fields",
                details=errors, status_code=400,
            )

        reason = data["reason"]

        # Find content item
        content_item = ContentItem.query.get(content_id)
        if content_item is None:
            return error_response("NOT_FOUND", "Content item not found", status_code=404)

        # Create moderation case
        case = ModerationCase(
            content_id=content_id,
            reporter_id=current.user_id,
            action=ModerationAction.REPORT.value,
            reason=reason,
        )
        db.session.add(case)

        # Set content quality_state to REPORTED if currently ACTIVE or REINSTATED
        before_state = content_item.quality_state
        if content_item.quality_state in (
            ContentQualityState.ACTIVE.value,
            ContentQualityState.REINSTATED.value,
        ):
            content_item.quality_state = ContentQualityState.REPORTED.value

        db.session.flush()

        # Audit event
        audit = AuditEvent(
            event_type=AuditEventType.CONTENT_REPORTED.value,
            actor_id=current.user_id,
            actor_ip=request.remote_addr,
            target_type="ContentItem",
            target_id=content_id,
            organization_id=content_item.organization_id,
            before_state=json.dumps({"quality_state": before_state}),
            after_state=json.dumps({
                "quality_state": content_item.quality_state,
                "moderation_case_id": case.id,
            }),
        )
        db.session.add(audit)
        db.session.commit()

        logger.info(
            "content", "report",
            f"Content reported: content_id={content_id} case_id={case.id} "
            f"reporter={current.user_id} reason={reason[:100]}",
        )

        return success_response(_serialize_moderation_case(case), status_code=201)

    except Exception as exc:
        db.session.rollback()
        logger.error("content", "report", f"Unexpected error: {exc}")
        return error_response("INTERNAL_ERROR", "An unexpected error occurred", status_code=500)


# ──────────────────────────────────────────
# POST /moderation/cases/<id>/decision
# ──────────────────────────────────────────
@content_bp.route("/moderation/cases/<case_id>/decision", methods=["POST"])
@require_auth
@require_permission("moderation:review")
def moderation_decision(case_id):
    try:
        current = g.current_user
        data = request.get_json(silent=True) or {}

        errors = validate_required(data, ["action", "decision_notes"])
        if errors:
            return error_response(
                "VALIDATION_ERROR", "Missing required fields",
                details=errors, status_code=400,
            )

        action = data["action"]
        decision_notes = data["decision_notes"]

        # Validate action
        if action not in (ModerationAction.SUPPRESS.value, ModerationAction.REINSTATE.value):
            return error_response(
                "VALIDATION_ERROR",
                "action must be 'SUPPRESS' or 'REINSTATE'",
                status_code=400,
            )

        # Load moderation case
        case = ModerationCase.query.get(case_id)
        if case is None:
            return error_response("NOT_FOUND", "Moderation case not found", status_code=404)

        # Load content item
        content_item = ContentItem.query.get(case.content_id)
        if content_item is None:
            return error_response("NOT_FOUND", "Associated content item not found", status_code=404)

        before_state = json.dumps({
            "case_action": case.action,
            "content_quality_state": content_item.quality_state,
        })

        # Apply decision
        now = datetime.now(timezone.utc)
        case.action = action
        case.decision_notes = decision_notes
        case.reviewer_id = current.user_id
        case.decided_at = now

        if action == ModerationAction.SUPPRESS.value:
            content_item.quality_state = ContentQualityState.SUPPRESSED.value
        elif action == ModerationAction.REINSTATE.value:
            content_item.quality_state = ContentQualityState.REINSTATED.value

        # Audit event
        audit = AuditEvent(
            event_type=AuditEventType.MODERATION_DECISION.value,
            actor_id=current.user_id,
            actor_ip=request.remote_addr,
            target_type="ModerationCase",
            target_id=case.id,
            organization_id=content_item.organization_id,
            before_state=before_state,
            after_state=json.dumps({
                "case_action": case.action,
                "content_quality_state": content_item.quality_state,
                "decision_notes": decision_notes,
            }),
        )
        db.session.add(audit)
        db.session.commit()

        logger.info(
            "moderation", "decision",
            f"Moderation decision: case_id={case.id} action={action} "
            f"reviewer={current.user_id} content_id={case.content_id}",
        )

        return success_response(_serialize_moderation_case(case))

    except Exception as exc:
        db.session.rollback()
        logger.error("moderation", "decision", f"Unexpected error: {exc}")
        return error_response("INTERNAL_ERROR", "An unexpected error occurred", status_code=500)


# ──────────────────────────────────────────
# POST /moderation/cases/<id>/appeal
# ──────────────────────────────────────────
@content_bp.route("/moderation/cases/<case_id>/appeal", methods=["POST"])
@require_auth
def moderation_appeal(case_id):
    try:
        current = g.current_user
        data = request.get_json(silent=True) or {}

        errors = validate_required(data, ["appeal_notes"])
        if errors:
            return error_response(
                "VALIDATION_ERROR", "Missing required fields",
                details=errors, status_code=400,
            )

        appeal_notes = data["appeal_notes"]

        # Validate appeal_notes minimum length
        if len(appeal_notes) < config.APPEAL_MIN_NOTES_LENGTH:
            return error_response(
                "VALIDATION_ERROR",
                f"appeal_notes must be at least {config.APPEAL_MIN_NOTES_LENGTH} characters",
                status_code=400,
            )

        # Load moderation case
        case = ModerationCase.query.get(case_id)
        if case is None:
            return error_response("NOT_FOUND", "Moderation case not found", status_code=404)

        # Load content item
        content_item = ContentItem.query.get(case.content_id)
        if content_item is None:
            return error_response("NOT_FOUND", "Associated content item not found", status_code=404)

        # Verify the caller is the content creator
        if content_item.creator_id != current.user_id:
            return error_response(
                "FORBIDDEN",
                "Only the content creator can appeal this decision",
                status_code=403,
            )

        # Verify content is SUPPRESSED
        if content_item.quality_state != ContentQualityState.SUPPRESSED.value:
            return error_response(
                "INVALID_STATE",
                "Can only appeal suppressed content",
                status_code=409,
            )

        # Verify no existing appeal
        if case.appealed_at is not None:
            return error_response(
                "CONFLICT",
                "This case has already been appealed",
                status_code=409,
            )

        # Verify within appeal window
        if case.decided_at is None:
            return error_response(
                "INVALID_STATE",
                "Cannot appeal a case that has no decision",
                status_code=409,
            )

        decided_at = case.decided_at
        if decided_at.tzinfo is None:
            decided_at = decided_at.replace(tzinfo=timezone.utc)
        appeal_deadline = decided_at + timedelta(days=config.APPEAL_WINDOW_DAYS)
        now = datetime.now(timezone.utc)
        if now > appeal_deadline:
            return error_response(
                "APPEAL_EXPIRED",
                f"Appeal window of {config.APPEAL_WINDOW_DAYS} days has expired",
                status_code=409,
            )

        # Set appeal fields
        case.appeal_notes = appeal_notes
        case.appealed_at = now
        case.action = ModerationAction.APPEAL.value

        # Audit event
        audit = AuditEvent(
            event_type=AuditEventType.MODERATION_APPEAL.value,
            actor_id=current.user_id,
            actor_ip=request.remote_addr,
            target_type="ModerationCase",
            target_id=case.id,
            organization_id=content_item.organization_id,
            after_state=json.dumps({
                "case_action": case.action,
                "appeal_notes": appeal_notes[:200],
            }),
        )
        db.session.add(audit)
        db.session.commit()

        logger.info(
            "moderation", "appeal",
            f"Appeal filed: case_id={case.id} content_id={case.content_id} "
            f"creator={current.user_id}",
        )

        return success_response(_serialize_moderation_case(case))

    except Exception as exc:
        db.session.rollback()
        logger.error("moderation", "appeal", f"Unexpected error: {exc}")
        return error_response("INTERNAL_ERROR", "An unexpected error occurred", status_code=500)


# ──────────────────────────────────────────
# POST /moderation/cases/<id>/appeal-decision
# ──────────────────────────────────────────
@content_bp.route("/moderation/cases/<case_id>/appeal-decision", methods=["POST"])
@require_auth
@require_permission("moderation:review")
def moderation_appeal_decision(case_id):
    try:
        current = g.current_user
        data = request.get_json(silent=True) or {}

        errors = validate_required(data, ["action", "appeal_decision_notes"])
        if errors:
            return error_response(
                "VALIDATION_ERROR", "Missing required fields",
                details=errors, status_code=400,
            )

        action = data["action"]
        appeal_decision_notes = data["appeal_decision_notes"]

        # Validate action
        if action not in (ModerationAction.APPEAL_APPROVED.value, ModerationAction.APPEAL_DENIED.value):
            return error_response(
                "VALIDATION_ERROR",
                "action must be 'APPEAL_APPROVED' or 'APPEAL_DENIED'",
                status_code=400,
            )

        # Load moderation case
        case = ModerationCase.query.get(case_id)
        if case is None:
            return error_response("NOT_FOUND", "Moderation case not found", status_code=404)

        # Verify appeal exists
        if case.appealed_at is None:
            return error_response(
                "INVALID_STATE",
                "No appeal has been filed for this case",
                status_code=409,
            )

        # Load content item
        content_item = ContentItem.query.get(case.content_id)
        if content_item is None:
            return error_response("NOT_FOUND", "Associated content item not found", status_code=404)

        before_state = json.dumps({
            "case_action": case.action,
            "content_quality_state": content_item.quality_state,
        })

        # Apply appeal decision
        now = datetime.now(timezone.utc)
        case.action = action
        case.appeal_decision_notes = appeal_decision_notes
        case.reviewer_id = current.user_id
        case.decided_at = now

        if action == ModerationAction.APPEAL_APPROVED.value:
            content_item.quality_state = ContentQualityState.REINSTATED.value
        # APPEAL_DENIED: keep content SUPPRESSED (no change needed)

        # Audit event
        audit = AuditEvent(
            event_type=AuditEventType.MODERATION_APPEAL_DECISION.value,
            actor_id=current.user_id,
            actor_ip=request.remote_addr,
            target_type="ModerationCase",
            target_id=case.id,
            organization_id=content_item.organization_id,
            before_state=before_state,
            after_state=json.dumps({
                "case_action": case.action,
                "content_quality_state": content_item.quality_state,
                "appeal_decision_notes": appeal_decision_notes,
            }),
        )
        db.session.add(audit)
        db.session.commit()

        logger.info(
            "moderation", "appeal-decision",
            f"Appeal decision: case_id={case.id} action={action} "
            f"reviewer={current.user_id} content_id={case.content_id}",
        )

        return success_response(_serialize_moderation_case(case))

    except Exception as exc:
        db.session.rollback()
        logger.error("moderation", "appeal-decision", f"Unexpected error: {exc}")
        return error_response("INTERNAL_ERROR", "An unexpected error occurred", status_code=500)
