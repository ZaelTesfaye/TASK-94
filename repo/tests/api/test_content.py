"""API tests for content governance and moderation endpoints."""
import uuid

import pytest


def _grant_moderation_permission(db):
    """Grant the admin user the moderation:review permission."""
    from src.models.models import Permission, UserPermission, User

    perm = Permission.query.filter_by(code="moderation:review").first()
    if not perm:
        perm = Permission(code="moderation:review", description="Can moderate content")
        db.session.add(perm)
        db.session.flush()

    admin = User.query.filter_by(username="admin").first()
    existing = UserPermission.query.filter_by(
        user_id=admin.id, permission_id=perm.id,
    ).first()
    if not existing:
        up = UserPermission(user_id=admin.id, permission_id=perm.id)
        db.session.add(up)

    db.session.commit()
    return perm


def _get_admin_headers_with_moderation(client, db):
    """Login as admin after granting moderation:review permission.

    The permission must be in the JWT claims. Since the access_token
    is created at login time from the user's role (platform_admin),
    the require_permission decorator checks g.current_user.permissions
    which comes from the JWT. We need the permission code in the token.

    Approach: assign the permission to the admin user, then login.
    The token's permissions list comes from the JWT payload which is
    built at login time. Looking at the code, the access_token only
    contains permissions from the payload explicitly passed, and
    login does not populate permissions from UserPermission table.

    So we need to work around this by patching the token or using
    the require_permission logic. Let's check the middleware...

    The middleware populates permissions from payload.get("permissions", []).
    The login endpoint calls create_access_token without permissions arg.
    So we need to ensure the admin token includes the permission.

    We'll use a direct approach: patch via create_access_token.
    """
    from src.models.models import User
    from src.security.tokens import create_access_token

    _grant_moderation_permission(db)
    admin = User.query.filter_by(username="admin").first()

    # Determine org_id
    from src.models.models import Membership
    membership = Membership.query.filter_by(user_id=admin.id, is_active=True).first()
    org_id = membership.organization_id if membership else None

    token = create_access_token(
        user_id=admin.id,
        username=admin.username,
        role=admin.role,
        organization_id=org_id,
        permissions=["moderation:review"],
    )
    return {"Authorization": f"Bearer {token}"}


class TestContentCreation:
    def test_create_content(self, client, member_user, org_setup, db):
        resp = client.post("/content", json={
            "title": "Test Article",
            "body": "This is a test article body with enough content.",
            "organization_id": org_setup["id"],
        }, headers=member_user["headers"])
        assert resp.status_code == 201
        data = resp.get_json()["data"]
        assert data["title"] == "Test Article"
        assert data["quality_state"] == "ACTIVE"

    def test_list_content(self, client, member_user, org_setup, db):
        client.post("/content", json={
            "title": "Listable Article",
            "body": "Body content here.",
            "organization_id": org_setup["id"],
        }, headers=member_user["headers"])

        resp = client.get(
            f"/content?organization_id={org_setup['id']}",
            headers=member_user["headers"],
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert len(body["data"]) >= 1

    def test_duplicate_detection(self, client, member_user, org_setup, db):
        title = f"Unique Title {uuid.uuid4().hex[:8]}"
        body_text = "Exact same body text for duplicate detection."

        # First creation
        resp1 = client.post("/content", json={
            "title": title,
            "body": body_text,
            "organization_id": org_setup["id"],
        }, headers=member_user["headers"])
        assert resp1.status_code == 201
        assert resp1.get_json()["data"]["quality_state"] == "ACTIVE"

        # Second creation with same title/body
        resp2 = client.post("/content", json={
            "title": title,
            "body": body_text,
            "organization_id": org_setup["id"],
        }, headers=member_user["headers"])
        assert resp2.status_code == 201
        assert resp2.get_json()["data"]["quality_state"] == "DUPLICATE_DEMOTED"


class TestContentRating:
    def test_rate_content(self, client, member_user, org_setup, db):
        # Create content
        resp = client.post("/content", json={
            "title": "Rateable Article",
            "body": "Content to rate.",
            "organization_id": org_setup["id"],
        }, headers=member_user["headers"])
        content_id = resp.get_json()["data"]["id"]

        # Rate it
        resp = client.post(f"/content/{content_id}/ratings", json={
            "score": 4,
        }, headers=member_user["headers"])
        assert resp.status_code in (200, 201)

        # Verify avg_rating is updated on the content item
        from src.models.models import ContentItem
        item = ContentItem.query.get(content_id)
        assert item.avg_rating == 4.0


class TestContentComment:
    def test_comment_on_content(self, client, member_user, org_setup, db):
        # Create content
        resp = client.post("/content", json={
            "title": "Commentable Article",
            "body": "Content to comment on.",
            "organization_id": org_setup["id"],
        }, headers=member_user["headers"])
        content_id = resp.get_json()["data"]["id"]

        # Comment
        resp = client.post(f"/content/{content_id}/comments", json={
            "body": "Great article, very informative!",
        }, headers=member_user["headers"])
        assert resp.status_code == 201
        data = resp.get_json()["data"]
        assert data["body"] == "Great article, very informative!"


class TestContentFavorite:
    def test_favorite_content(self, client, member_user, org_setup, db):
        # Create content
        resp = client.post("/content", json={
            "title": "Favoritable Article",
            "body": "Content to favorite.",
            "organization_id": org_setup["id"],
        }, headers=member_user["headers"])
        content_id = resp.get_json()["data"]["id"]

        # Favorite
        resp1 = client.post(f"/content/{content_id}/favorite",
                            headers=member_user["headers"])
        assert resp1.status_code == 201

        # Favorite again (idempotent)
        resp2 = client.post(f"/content/{content_id}/favorite",
                            headers=member_user["headers"])
        assert resp2.status_code == 200

    def test_unfavorite_content(self, client, member_user, org_setup, db):
        # Create content
        resp = client.post("/content", json={
            "title": "Unfavoritable Article",
            "body": "Content to unfavorite.",
            "organization_id": org_setup["id"],
        }, headers=member_user["headers"])
        content_id = resp.get_json()["data"]["id"]

        # Favorite then unfavorite
        client.post(f"/content/{content_id}/favorite",
                     headers=member_user["headers"])
        resp = client.delete(f"/content/{content_id}/favorite",
                             headers=member_user["headers"])
        assert resp.status_code == 204


class TestContentDownload:
    def test_download_content(self, client, member_user, org_setup, db):
        # Create content
        resp = client.post("/content", json={
            "title": "Downloadable Article",
            "body": "Content to download.",
            "organization_id": org_setup["id"],
        }, headers=member_user["headers"])
        content_id = resp.get_json()["data"]["id"]

        # Download
        resp = client.post(f"/content/{content_id}/download",
                           headers=member_user["headers"])
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert data["download_count"] == 1


class TestContentModeration:
    def test_report_content(self, client, member_user, org_setup, db):
        # Create content
        resp = client.post("/content", json={
            "title": "Reportable Article",
            "body": "Content to report.",
            "organization_id": org_setup["id"],
        }, headers=member_user["headers"])
        content_id = resp.get_json()["data"]["id"]

        # Report
        resp = client.post(f"/content/{content_id}/report", json={
            "reason": "Inappropriate content that violates guidelines.",
        }, headers=member_user["headers"])
        assert resp.status_code == 201

        # Verify quality_state changed to REPORTED
        from src.models.models import ContentItem
        item = ContentItem.query.get(content_id)
        assert item.quality_state == "REPORTED"

    def test_moderation_suppress(self, client, member_user, org_setup, db):
        # Create content
        resp = client.post("/content", json={
            "title": "Suppressible Article",
            "body": "Content to suppress after reporting.",
            "organization_id": org_setup["id"],
        }, headers=member_user["headers"])
        content_id = resp.get_json()["data"]["id"]

        # Report
        report_resp = client.post(f"/content/{content_id}/report", json={
            "reason": "Violates community guidelines.",
        }, headers=member_user["headers"])
        case_id = report_resp.get_json()["data"]["id"]

        # Admin suppresses (needs moderation:review permission in token)
        mod_headers = _get_admin_headers_with_moderation(client, db)
        resp = client.post(f"/moderation/cases/{case_id}/decision", json={
            "action": "SUPPRESS",
            "decision_notes": "Content violates policy.",
        }, headers=mod_headers)
        assert resp.status_code == 200

        from src.models.models import ContentItem
        item = ContentItem.query.get(content_id)
        assert item.quality_state == "SUPPRESSED"

    def test_appeal_and_approve(self, client, member_user, org_setup, db):
        # Create content
        resp = client.post("/content", json={
            "title": "Appealable Article",
            "body": "Content that will be suppressed then appealed.",
            "organization_id": org_setup["id"],
        }, headers=member_user["headers"])
        content_id = resp.get_json()["data"]["id"]

        # Report
        report_resp = client.post(f"/content/{content_id}/report", json={
            "reason": "Seems inappropriate at first glance.",
        }, headers=member_user["headers"])
        case_id = report_resp.get_json()["data"]["id"]

        # Suppress
        mod_headers = _get_admin_headers_with_moderation(client, db)
        client.post(f"/moderation/cases/{case_id}/decision", json={
            "action": "SUPPRESS",
            "decision_notes": "Suppressed pending review.",
        }, headers=mod_headers)

        # Creator appeals
        appeal_notes = "I believe this content is appropriate and should be reinstated. " \
                       "It follows all community guidelines and provides educational value."
        resp = client.post(f"/moderation/cases/{case_id}/appeal", json={
            "appeal_notes": appeal_notes,
        }, headers=member_user["headers"])
        assert resp.status_code == 200

        # Admin approves appeal
        resp = client.post(f"/moderation/cases/{case_id}/appeal-decision", json={
            "action": "APPEAL_APPROVED",
            "appeal_decision_notes": "Content is appropriate after review.",
        }, headers=mod_headers)
        assert resp.status_code == 200

        from src.models.models import ContentItem
        item = ContentItem.query.get(content_id)
        assert item.quality_state == "REINSTATED"
