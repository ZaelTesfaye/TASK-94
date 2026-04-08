"""Analytics and export endpoints - plan section 6.6."""

from datetime import datetime, timezone, timedelta

from flask import Blueprint, request, g, send_file
from sqlalchemy import func, and_

import hashlib
import json
import csv
import os
import io

from src.models.base import db
from src.models.models import (
    LearningEvent, Question, Attempt, ContentItem, Export, AuditEvent,
    UserCohort, User,
)
from src.models.enums import (
    LearningEventType, DifficultyBucket, DIFFICULTY_THRESHOLDS,
    ExportStatus, AuditEventType, RoleType,
)
from src.security.auth_middleware import require_auth, require_role
from src.utils.responses import success_response, error_response, list_response
from src.utils.pagination import paginate_query
from src.logging import logger
from src.config import config

analytics_bp = Blueprint("analytics", __name__, url_prefix="")


# ──────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────

def _is_platform_admin() -> bool:
    """Check if the current user is a platform admin."""
    return getattr(g.current_user, "role", None) == RoleType.PLATFORM_ADMIN.value


def _resolve_org_id():
    """Resolve organization_id: platform admins may pass it as a query param,
    otherwise use the token's org_id."""
    if _is_platform_admin():
        org_id = request.args.get("organization_id") or getattr(g.current_user, "organization_id", None)
    else:
        org_id = getattr(g.current_user, "organization_id", None)
    return org_id


def _parse_date(value: str | None, default=None) -> datetime | None:
    """Parse an ISO-8601 date string, returning *default* on failure."""
    if not value:
        return default
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return default


def _classify_difficulty(correct_rate: float) -> str:
    """Map a correct_rate to a DifficultyBucket using DIFFICULTY_THRESHOLDS."""
    for threshold, bucket in DIFFICULTY_THRESHOLDS:
        if correct_rate >= threshold:
            return bucket.value
    return DifficultyBucket.VERY_HARD.value


def _cohort_user_ids(cohort_tag: str, organization_id: str) -> list[str]:
    """Return list of user IDs belonging to a cohort within an org."""
    rows = (
        UserCohort.query
        .filter_by(cohort_tag=cohort_tag, organization_id=organization_id)
        .with_entities(UserCohort.user_id)
        .all()
    )
    return [r.user_id for r in rows]


# ──────────────────────────────────────────
# CSV generation helper
# ──────────────────────────────────────────

def _generate_csv(export_type: str, parameters: dict | None, organization_id: str, file_path: str):
    """Query data for *export_type* and write a CSV to *file_path*."""
    parameters = parameters or {}

    start_date = _parse_date(parameters.get("start_date"))
    end_date = _parse_date(parameters.get("end_date"))
    content_id = parameters.get("content_id")

    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    with open(file_path, "w", newline="", encoding="utf-8") as fh:
        if export_type == "learning_events":
            writer = csv.writer(fh)
            writer.writerow(["id", "user_id", "event_type", "content_id", "created_at"])

            query = LearningEvent.query.filter_by(organization_id=organization_id)
            if start_date:
                query = query.filter(LearningEvent.created_at >= start_date)
            if end_date:
                query = query.filter(LearningEvent.created_at <= end_date)
            if parameters.get("event_type"):
                query = query.filter(LearningEvent.event_type == parameters["event_type"])
            if content_id:
                query = query.filter(LearningEvent.content_id == content_id)

            for ev in query.yield_per(500):
                writer.writerow([
                    ev.id, ev.user_id, ev.event_type,
                    ev.content_id, ev.created_at.isoformat() if ev.created_at else "",
                ])

        elif export_type == "completions":
            writer = csv.writer(fh)
            writer.writerow(["user_id", "content_id", "content_type", "completed_at"])

            completion_types = [
                LearningEventType.MODULE_COMPLETE.value,
                LearningEventType.COURSE_COMPLETE.value,
            ]
            query = (
                LearningEvent.query
                .filter(
                    LearningEvent.organization_id == organization_id,
                    LearningEvent.event_type.in_(completion_types),
                )
            )
            if start_date:
                query = query.filter(LearningEvent.created_at >= start_date)
            if end_date:
                query = query.filter(LearningEvent.created_at <= end_date)
            if content_id:
                query = query.filter(LearningEvent.content_id == content_id)

            for ev in query.yield_per(500):
                content_type = ""
                if ev.content_id:
                    ci = ContentItem.query.get(ev.content_id)
                    content_type = ci.content_type if ci else ""
                writer.writerow([
                    ev.user_id, ev.content_id, content_type,
                    ev.created_at.isoformat() if ev.created_at else "",
                ])

        elif export_type == "attempts":
            writer = csv.writer(fh)
            writer.writerow(["user_id", "question_id", "answer_given", "is_correct", "created_at"])

            query = Attempt.query.filter_by(organization_id=organization_id)
            if start_date:
                query = query.filter(Attempt.created_at >= start_date)
            if end_date:
                query = query.filter(Attempt.created_at <= end_date)
            if parameters.get("question_id"):
                query = query.filter(Attempt.question_id == parameters["question_id"])

            for att in query.yield_per(500):
                writer.writerow([
                    att.user_id, att.question_id, att.answer_given,
                    att.is_correct,
                    att.created_at.isoformat() if att.created_at else "",
                ])

        elif export_type == "content_metrics":
            writer = csv.writer(fh)
            writer.writerow(["content_id", "title", "avg_rating", "rating_count", "view_count", "download_count"])

            query = ContentItem.query.filter_by(organization_id=organization_id)
            if content_id:
                query = query.filter(ContentItem.id == content_id)

            for ci in query.yield_per(500):
                writer.writerow([
                    ci.id, ci.title, ci.avg_rating, ci.rating_count,
                    ci.view_count, ci.download_count,
                ])

        else:
            raise ValueError(f"Unknown export_type: {export_type}")


def _export_to_dict(export: Export) -> dict:
    """Serialize an Export model to a dict."""
    return {
        "id": export.id,
        "requester_id": export.requester_id,
        "organization_id": export.organization_id,
        "export_type": export.export_type,
        "parameters": json.loads(export.parameters_json) if export.parameters_json else None,
        "parameters_hash": export.parameters_hash,
        "status": export.status,
        "file_path": export.file_path,
        "error_message": export.error_message,
        "created_at": export.created_at.isoformat() if export.created_at else None,
        "completed_at": export.completed_at.isoformat() if export.completed_at else None,
    }


# ──────────────────────────────────────────
# Analytics endpoints
# ──────────────────────────────────────────

@analytics_bp.route("/analytics/learning-behavior", methods=["GET"])
@require_auth
def analytics_learning_behavior():
    """Aggregated learning-event counts by event_type for an org."""
    try:
        org_id = _resolve_org_id()
        if not org_id:
            return error_response("ORG_REQUIRED", "Organization context is required", status_code=400)

        start_date = _parse_date(request.args.get("start_date"))
        end_date = _parse_date(request.args.get("end_date"))
        event_type = request.args.get("event_type")
        cohort_tag = request.args.get("cohort_tag")
        user_id = request.args.get("user_id")

        if not start_date:
            return error_response("VALIDATION_ERROR", "start_date is required", status_code=400)

        query = (
            db.session.query(
                LearningEvent.event_type,
                func.count(LearningEvent.id).label("count"),
            )
            .filter(LearningEvent.organization_id == org_id)
            .filter(LearningEvent.created_at >= start_date)
        )

        if end_date:
            query = query.filter(LearningEvent.created_at <= end_date)
        if event_type:
            query = query.filter(LearningEvent.event_type == event_type)
        if user_id:
            query = query.filter(LearningEvent.user_id == user_id)
        if cohort_tag:
            cohort_users = _cohort_user_ids(cohort_tag, org_id)
            if not cohort_users:
                return success_response({"results": [], "total_events": 0})
            query = query.filter(LearningEvent.user_id.in_(cohort_users))

        query = query.group_by(LearningEvent.event_type)
        rows = query.all()

        results = [{"event_type": row.event_type, "count": row.count} for row in rows]
        total_events = sum(r["count"] for r in results)

        logger.info("analytics", "learning-behavior", f"Query returned {len(results)} event types for org={org_id}")
        return success_response({"results": results, "total_events": total_events})

    except Exception as exc:
        logger.error("analytics", "learning-behavior", f"Error: {exc}")
        return error_response("INTERNAL_ERROR", "Failed to retrieve learning behavior analytics", status_code=500)


@analytics_bp.route("/analytics/completion", methods=["GET"])
@require_auth
def analytics_completion():
    """Completion analytics: rate and breakdown by content_type."""
    try:
        org_id = _resolve_org_id()
        if not org_id:
            return error_response("ORG_REQUIRED", "Organization context is required", status_code=400)

        start_date = _parse_date(request.args.get("start_date"))
        end_date = _parse_date(request.args.get("end_date"))
        content_type = request.args.get("content_type")
        cohort_tag = request.args.get("cohort_tag")

        if not start_date:
            return error_response("VALIDATION_ERROR", "start_date is required", status_code=400)

        # Determine user pool
        cohort_users = None
        if cohort_tag:
            cohort_users = _cohort_user_ids(cohort_tag, org_id)
            if not cohort_users:
                return success_response({
                    "total_users": 0,
                    "users_with_completion": 0,
                    "completion_rate": 0.0,
                    "breakdown": [],
                })

        # Total unique users with any learning event in range
        total_users_q = (
            db.session.query(func.count(func.distinct(LearningEvent.user_id)))
            .filter(
                LearningEvent.organization_id == org_id,
                LearningEvent.created_at >= start_date,
            )
        )
        if end_date:
            total_users_q = total_users_q.filter(LearningEvent.created_at <= end_date)
        if cohort_users is not None:
            total_users_q = total_users_q.filter(LearningEvent.user_id.in_(cohort_users))

        total_users = total_users_q.scalar() or 0

        # Completion events
        completion_types = [
            LearningEventType.MODULE_COMPLETE.value,
            LearningEventType.COURSE_COMPLETE.value,
        ]

        completion_q = (
            LearningEvent.query
            .filter(
                LearningEvent.organization_id == org_id,
                LearningEvent.event_type.in_(completion_types),
                LearningEvent.created_at >= start_date,
            )
        )
        if end_date:
            completion_q = completion_q.filter(LearningEvent.created_at <= end_date)
        if cohort_users is not None:
            completion_q = completion_q.filter(LearningEvent.user_id.in_(cohort_users))
        if content_type:
            # Join to ContentItem to filter by content_type
            completion_q = completion_q.join(
                ContentItem, LearningEvent.content_id == ContentItem.id
            ).filter(ContentItem.content_type == content_type)

        users_with_completion = (
            db.session.query(func.count(func.distinct(LearningEvent.user_id)))
            .filter(
                LearningEvent.organization_id == org_id,
                LearningEvent.event_type.in_(completion_types),
                LearningEvent.created_at >= start_date,
            )
        )
        if end_date:
            users_with_completion = users_with_completion.filter(LearningEvent.created_at <= end_date)
        if cohort_users is not None:
            users_with_completion = users_with_completion.filter(LearningEvent.user_id.in_(cohort_users))

        users_completed = users_with_completion.scalar() or 0

        completion_rate = (users_completed / total_users) if total_users > 0 else 0.0

        # Breakdown by content_type
        breakdown_q = (
            db.session.query(
                ContentItem.content_type,
                func.count(LearningEvent.id).label("count"),
            )
            .join(ContentItem, LearningEvent.content_id == ContentItem.id)
            .filter(
                LearningEvent.organization_id == org_id,
                LearningEvent.event_type.in_(completion_types),
                LearningEvent.created_at >= start_date,
            )
        )
        if end_date:
            breakdown_q = breakdown_q.filter(LearningEvent.created_at <= end_date)
        if cohort_users is not None:
            breakdown_q = breakdown_q.filter(LearningEvent.user_id.in_(cohort_users))

        breakdown_q = breakdown_q.group_by(ContentItem.content_type)
        breakdown_rows = breakdown_q.all()

        breakdown = [
            {"content_type": row.content_type, "count": row.count}
            for row in breakdown_rows
        ]

        logger.info("analytics", "completion", f"Completion rate={completion_rate:.2f} for org={org_id}")
        return success_response({
            "total_users": total_users,
            "users_with_completion": users_completed,
            "completion_rate": round(completion_rate, 4),
            "breakdown": breakdown,
        })

    except Exception as exc:
        logger.error("analytics", "completion", f"Error: {exc}")
        return error_response("INTERNAL_ERROR", "Failed to retrieve completion analytics", status_code=500)


@analytics_bp.route("/analytics/wrong-answers", methods=["GET"])
@require_auth
def analytics_wrong_answers():
    """Top questions by wrong answer count."""
    try:
        org_id = _resolve_org_id()
        if not org_id:
            return error_response("ORG_REQUIRED", "Organization context is required", status_code=400)

        start_date = _parse_date(request.args.get("start_date"))
        end_date = _parse_date(request.args.get("end_date"))
        content_id = request.args.get("content_id")
        question_id = request.args.get("question_id")
        limit = request.args.get("limit", 20, type=int)

        if not start_date:
            return error_response("VALIDATION_ERROR", "start_date is required", status_code=400)

        # Wrong attempts grouped by question
        wrong_q = (
            db.session.query(
                Attempt.question_id,
                Question.question_text,
                func.count(Attempt.id).label("wrong_count"),
            )
            .join(Question, Attempt.question_id == Question.id)
            .filter(
                Attempt.organization_id == org_id,
                Attempt.is_correct == False,  # noqa: E712
                Attempt.created_at >= start_date,
            )
        )
        if end_date:
            wrong_q = wrong_q.filter(Attempt.created_at <= end_date)
        if content_id:
            wrong_q = wrong_q.filter(Question.content_id == content_id)
        if question_id:
            wrong_q = wrong_q.filter(Attempt.question_id == question_id)

        wrong_q = (
            wrong_q
            .group_by(Attempt.question_id, Question.question_text)
            .order_by(func.count(Attempt.id).desc())
            .limit(limit)
        )
        wrong_rows = wrong_q.all()

        # For each question, also fetch total attempts and compute correct_rate
        results = []
        for row in wrong_rows:
            total_q = (
                db.session.query(func.count(Attempt.id))
                .filter(
                    Attempt.question_id == row.question_id,
                    Attempt.organization_id == org_id,
                    Attempt.created_at >= start_date,
                )
            )
            if end_date:
                total_q = total_q.filter(Attempt.created_at <= end_date)
            total_attempts = total_q.scalar() or 0

            correct_rate = ((total_attempts - row.wrong_count) / total_attempts) if total_attempts > 0 else 0.0

            results.append({
                "question_id": row.question_id,
                "question_text": row.question_text,
                "wrong_count": row.wrong_count,
                "total_attempts": total_attempts,
                "correct_rate": round(correct_rate, 4),
            })

        logger.info("analytics", "wrong-answers", f"Returned {len(results)} questions for org={org_id}")
        return success_response({"results": results})

    except Exception as exc:
        logger.error("analytics", "wrong-answers", f"Error: {exc}")
        return error_response("INTERNAL_ERROR", "Failed to retrieve wrong-answer analytics", status_code=500)


@analytics_bp.route("/analytics/difficulty", methods=["GET"])
@require_auth
def analytics_difficulty():
    """Difficulty distribution for questions based on correct_rate."""
    try:
        org_id = _resolve_org_id()
        if not org_id:
            return error_response("ORG_REQUIRED", "Organization context is required", status_code=400)

        start_date = _parse_date(request.args.get("start_date"))
        end_date = _parse_date(request.args.get("end_date"))
        content_id = request.args.get("content_id")

        if not start_date:
            return error_response("VALIDATION_ERROR", "start_date is required", status_code=400)

        # All questions in scope
        q_query = Question.query.filter_by(organization_id=org_id)
        if content_id:
            q_query = q_query.filter(Question.content_id == content_id)

        questions = q_query.all()

        results = []
        summary = {"easy_count": 0, "medium_count": 0, "hard_count": 0, "very_hard_count": 0}

        for question in questions:
            # Compute attempt stats within date range
            total_q = (
                db.session.query(func.count(Attempt.id))
                .filter(
                    Attempt.question_id == question.id,
                    Attempt.organization_id == org_id,
                    Attempt.created_at >= start_date,
                )
            )
            if end_date:
                total_q = total_q.filter(Attempt.created_at <= end_date)
            total_attempts = total_q.scalar() or 0

            if total_attempts == 0:
                continue

            correct_q = (
                db.session.query(func.count(Attempt.id))
                .filter(
                    Attempt.question_id == question.id,
                    Attempt.organization_id == org_id,
                    Attempt.is_correct == True,  # noqa: E712
                    Attempt.created_at >= start_date,
                )
            )
            if end_date:
                correct_q = correct_q.filter(Attempt.created_at <= end_date)
            correct_attempts = correct_q.scalar() or 0

            correct_rate = correct_attempts / total_attempts
            difficulty_bucket = _classify_difficulty(correct_rate)

            results.append({
                "question_id": question.id,
                "question_text": question.question_text,
                "total_attempts": total_attempts,
                "correct_rate": round(correct_rate, 4),
                "difficulty_bucket": difficulty_bucket,
            })

            # Update summary
            if difficulty_bucket == DifficultyBucket.EASY.value:
                summary["easy_count"] += 1
            elif difficulty_bucket == DifficultyBucket.MEDIUM.value:
                summary["medium_count"] += 1
            elif difficulty_bucket == DifficultyBucket.HARD.value:
                summary["hard_count"] += 1
            elif difficulty_bucket == DifficultyBucket.VERY_HARD.value:
                summary["very_hard_count"] += 1

        logger.info("analytics", "difficulty", f"Classified {len(results)} questions for org={org_id}")
        return success_response({"results": results, "summary": summary})

    except Exception as exc:
        logger.error("analytics", "difficulty", f"Error: {exc}")
        return error_response("INTERNAL_ERROR", "Failed to retrieve difficulty analytics", status_code=500)


@analytics_bp.route("/analytics/course-effectiveness", methods=["GET"])
@require_auth
def analytics_course_effectiveness():
    """Course/module effectiveness metrics."""
    try:
        org_id = _resolve_org_id()
        if not org_id:
            return error_response("ORG_REQUIRED", "Organization context is required", status_code=400)

        start_date = _parse_date(request.args.get("start_date"))
        end_date = _parse_date(request.args.get("end_date"))
        content_id_filter = request.args.get("content_id")

        if not start_date:
            return error_response("VALIDATION_ERROR", "start_date is required", status_code=400)

        # Content items of type COURSE or MODULE
        ci_query = ContentItem.query.filter(
            ContentItem.organization_id == org_id,
            ContentItem.content_type.in_(["COURSE", "MODULE"]),
        )
        if content_id_filter:
            ci_query = ci_query.filter(ContentItem.id == content_id_filter)

        content_items = ci_query.all()

        completion_types = [
            LearningEventType.MODULE_COMPLETE.value,
            LearningEventType.COURSE_COMPLETE.value,
        ]

        results = []
        for ci in content_items:
            # Total learning events for this content
            events_q = (
                db.session.query(func.count(LearningEvent.id))
                .filter(
                    LearningEvent.organization_id == org_id,
                    LearningEvent.content_id == ci.id,
                    LearningEvent.created_at >= start_date,
                )
            )
            if end_date:
                events_q = events_q.filter(LearningEvent.created_at <= end_date)
            total_events = events_q.scalar() or 0

            # Completion events
            completions_q = (
                db.session.query(func.count(LearningEvent.id))
                .filter(
                    LearningEvent.organization_id == org_id,
                    LearningEvent.content_id == ci.id,
                    LearningEvent.event_type.in_(completion_types),
                    LearningEvent.created_at >= start_date,
                )
            )
            if end_date:
                completions_q = completions_q.filter(LearningEvent.created_at <= end_date)
            completions = completions_q.scalar() or 0

            # Unique users
            unique_users_q = (
                db.session.query(func.count(func.distinct(LearningEvent.user_id)))
                .filter(
                    LearningEvent.organization_id == org_id,
                    LearningEvent.content_id == ci.id,
                    LearningEvent.created_at >= start_date,
                )
            )
            if end_date:
                unique_users_q = unique_users_q.filter(LearningEvent.created_at <= end_date)
            unique_users = unique_users_q.scalar() or 0

            engagement_score = (total_events / unique_users) if unique_users > 0 else 0.0

            results.append({
                "content_id": ci.id,
                "title": ci.title,
                "content_type": ci.content_type,
                "total_events": total_events,
                "completions": completions,
                "avg_rating": round(ci.avg_rating, 4) if ci.avg_rating else 0.0,
                "engagement_score": round(engagement_score, 4),
            })

        logger.info("analytics", "course-effectiveness", f"Returned {len(results)} items for org={org_id}")
        return success_response({"results": results})

    except Exception as exc:
        logger.error("analytics", "course-effectiveness", f"Error: {exc}")
        return error_response("INTERNAL_ERROR", "Failed to retrieve course effectiveness analytics", status_code=500)


# ──────────────────────────────────────────
# Export endpoints
# ──────────────────────────────────────────

@analytics_bp.route("/exports", methods=["POST"])
@require_auth
def create_export():
    """Create and synchronously generate an export CSV."""
    try:
        data = request.get_json(silent=True) or {}

        export_type = data.get("export_type")
        parameters = data.get("parameters") or {}
        organization_id = data.get("organization_id")

        if not export_type:
            return error_response("VALIDATION_ERROR", "export_type is required", status_code=400)
        valid_types = {"learning_events", "completions", "attempts", "content_metrics"}
        if export_type not in valid_types:
            return error_response(
                "VALIDATION_ERROR",
                f"export_type must be one of: {', '.join(sorted(valid_types))}",
                status_code=400,
            )
        if not organization_id:
            return error_response("VALIDATION_ERROR", "organization_id is required", status_code=400)

        # Org-scope check: non-platform-admins can only export their own org
        if not _is_platform_admin():
            if organization_id != getattr(g.current_user, "organization_id", None):
                return error_response("FORBIDDEN", "Cannot export for another organization", status_code=403)

        current_user = g.current_user
        requester_id = current_user.user_id

        # Dedupe check
        parameters_hash = hashlib.sha256(
            json.dumps(parameters, sort_keys=True).encode("utf-8")
        ).hexdigest()

        dedupe_window = datetime.now(timezone.utc) - timedelta(hours=config.EXPORT_DEDUPE_WINDOW_HOURS)
        existing = (
            Export.query
            .filter(
                Export.requester_id == requester_id,
                Export.export_type == export_type,
                Export.parameters_hash == parameters_hash,
                Export.created_at >= dedupe_window,
            )
            .order_by(Export.created_at.desc())
            .first()
        )
        if existing:
            logger.info("analytics", "export", f"Dedupe hit for export_type={export_type} user={requester_id}")
            return success_response(
                {
                    "export": _export_to_dict(existing),
                    "message": "duplicate_within_window",
                },
                status_code=200,
            )

        # Create Export record
        export = Export(
            requester_id=requester_id,
            organization_id=organization_id,
            export_type=export_type,
            parameters_json=json.dumps(parameters, sort_keys=True) if parameters else None,
            parameters_hash=parameters_hash,
            status=ExportStatus.PENDING.value,
        )
        db.session.add(export)
        db.session.flush()  # get id before file generation

        file_path = os.path.join(config.EXPORT_DIR, f"{export.id}.csv")

        try:
            _generate_csv(export_type, parameters, organization_id, file_path)
            export.status = ExportStatus.COMPLETED.value
            export.file_path = file_path
            export.completed_at = datetime.now(timezone.utc)
        except Exception as gen_exc:
            export.status = ExportStatus.FAILED.value
            export.error_message = str(gen_exc)
            logger.error("analytics", "export", f"CSV generation failed: {gen_exc}")

        # Audit event
        audit = AuditEvent(
            event_type=AuditEventType.EXPORT_CREATED.value,
            actor_id=requester_id,
            actor_ip=request.remote_addr,
            target_type="Export",
            target_id=export.id,
            organization_id=organization_id,
            metadata_json=json.dumps({
                "export_type": export_type,
                "status": export.status,
            }),
        )
        db.session.add(audit)
        db.session.commit()

        logger.info("analytics", "export", f"Export created id={export.id} status={export.status}")
        return success_response({"export": _export_to_dict(export)}, status_code=201)

    except Exception as exc:
        db.session.rollback()
        logger.error("analytics", "export", f"Error creating export: {exc}")
        return error_response("INTERNAL_ERROR", "Failed to create export", status_code=500)


@analytics_bp.route("/exports", methods=["GET"])
@require_auth
def list_exports():
    """List exports, org-scoped with optional filters and pagination."""
    try:
        org_id = _resolve_org_id()
        if not org_id:
            return error_response("ORG_REQUIRED", "Organization context is required", status_code=400)

        query = Export.query.filter_by(organization_id=org_id)

        # Filters
        status = request.args.get("status")
        if status:
            query = query.filter(Export.status == status)

        export_type = request.args.get("export_type")
        if export_type:
            query = query.filter(Export.export_type == export_type)

        query = query.order_by(Export.created_at.desc())

        page = request.args.get("page", 1, type=int)
        per_page = request.args.get("per_page", config.DEFAULT_PAGE_SIZE, type=int)

        result = paginate_query(query, page, per_page)

        exports_data = [_export_to_dict(e) for e in result["items"]]

        logger.info("analytics", "exports-list", f"Listed {len(exports_data)} exports for org={org_id}")
        return list_response(exports_data, result["pagination"])

    except Exception as exc:
        logger.error("analytics", "exports-list", f"Error: {exc}")
        return error_response("INTERNAL_ERROR", "Failed to list exports", status_code=500)


@analytics_bp.route("/exports/<export_id>/download", methods=["GET"])
@require_auth
def download_export(export_id):
    """Download a completed export CSV."""
    try:
        export = Export.query.get(export_id)
        if not export:
            return error_response("NOT_FOUND", "Export not found", status_code=404)

        # Ownership / org-scope check
        current_user = g.current_user
        if not _is_platform_admin():
            if export.organization_id != getattr(current_user, "organization_id", None):
                if export.requester_id != current_user.user_id:
                    return error_response("FORBIDDEN", "Access denied", status_code=403)

        if export.status != ExportStatus.COMPLETED.value:
            return error_response(
                "EXPORT_NOT_READY",
                f"Export status is {export.status}, must be COMPLETED",
                status_code=400,
            )

        if not export.file_path or not os.path.exists(export.file_path):
            return error_response("FILE_NOT_FOUND", "Export file is missing", status_code=404)

        # Audit event
        audit = AuditEvent(
            event_type=AuditEventType.EXPORT_DOWNLOADED.value,
            actor_id=current_user.user_id,
            actor_ip=request.remote_addr,
            target_type="Export",
            target_id=export.id,
            organization_id=export.organization_id,
        )
        db.session.add(audit)
        db.session.commit()

        logger.info("analytics", "export-download", f"Export {export_id} downloaded by user={current_user.user_id}")
        return send_file(
            export.file_path,
            mimetype="text/csv",
            as_attachment=True,
            download_name=f"{export.export_type}_{export.id}.csv",
        )

    except Exception as exc:
        db.session.rollback()
        logger.error("analytics", "export-download", f"Error: {exc}")
        return error_response("INTERNAL_ERROR", "Failed to download export", status_code=500)
