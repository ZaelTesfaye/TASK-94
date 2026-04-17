"""Tests for prompt compliance fixes: role semantics, device blacklist cooldown,
per-identity rate limiting, burst config, and content recommendations."""

import uuid
from datetime import datetime, timezone, timedelta

import pytest


class TestMembershipRoleInToken:
    """Token role must come from membership role, with platform_admin preserved."""

    def test_login_token_uses_membership_role(self, client, db):
        """When a user has a membership, the JWT role claim should reflect
        the membership role, not the global User.role."""
        from src.models.models import User, Membership, Organization
        from src.models.enums import RoleType
        from src.security.tokens import decode_token

        # Register a guest (User.role = 'guest')
        username = f"memrole_{uuid.uuid4().hex[:8]}"
        reg_resp = client.post("/auth/register-guest", json={
            "username": username,
            "password": "SecurePass1!",
        })
        user_id = reg_resp.get_json()["data"]["user"]["id"]

        # Verify user's global role is guest
        user = User.query.get(user_id)
        assert user.role == RoleType.GUEST.value

        # Create org + membership with role=org_admin
        org = Organization(name="RoleTest Org", slug=f"roletest-{uuid.uuid4().hex[:6]}")
        db.session.add(org)
        db.session.flush()

        membership = Membership(
            user_id=user_id,
            organization_id=org.id,
            role=RoleType.ORG_ADMIN.value,
            is_active=True,
        )
        db.session.add(membership)
        db.session.commit()

        # Login and check the token's role claim
        login_resp = client.post("/auth/login", json={
            "username": username,
            "password": "SecurePass1!",
        })
        assert login_resp.status_code == 200
        token = login_resp.get_json()["data"]["access_token"]
        payload = decode_token(token)

        assert payload["role"] == RoleType.ORG_ADMIN.value
        assert payload["org_id"] == org.id

    def test_refresh_token_uses_membership_role(self, client, db):
        """Refreshed token should also use the membership role."""
        from src.models.models import Membership, Organization
        from src.models.enums import RoleType
        from src.security.tokens import decode_token

        username = f"refrole_{uuid.uuid4().hex[:8]}"
        reg_resp = client.post("/auth/register-guest", json={
            "username": username,
            "password": "SecurePass1!",
        })
        user_id = reg_resp.get_json()["data"]["user"]["id"]

        org = Organization(name="RefRole Org", slug=f"refrole-{uuid.uuid4().hex[:6]}")
        db.session.add(org)
        db.session.flush()
        membership = Membership(
            user_id=user_id,
            organization_id=org.id,
            role=RoleType.MEMBER.value,
            is_active=True,
        )
        db.session.add(membership)
        db.session.commit()

        # Login
        login_resp = client.post("/auth/login", json={
            "username": username,
            "password": "SecurePass1!",
        })
        refresh_token = login_resp.get_json()["data"]["refresh_token"]

        # Refresh
        refresh_resp = client.post("/auth/refresh", json={
            "refresh_token": refresh_token,
        })
        assert refresh_resp.status_code == 200
        new_token = refresh_resp.get_json()["data"]["access_token"]
        payload = decode_token(new_token)

        assert payload["role"] == RoleType.MEMBER.value

    def test_no_membership_falls_back_to_user_role(self, client, db):
        """Without a membership, the token should use User.role."""
        from src.security.tokens import decode_token
        from src.models.enums import RoleType

        username = f"norole_{uuid.uuid4().hex[:8]}"
        reg_resp = client.post("/auth/register-guest", json={
            "username": username,
            "password": "SecurePass1!",
        })
        assert reg_resp.status_code == 201

        login_resp = client.post("/auth/login", json={
            "username": username,
            "password": "SecurePass1!",
        })
        token = login_resp.get_json()["data"]["access_token"]
        payload = decode_token(token)
        assert payload["role"] == RoleType.GUEST.value

    def test_platform_admin_not_downgraded_by_membership(self, client, db):
        """A platform_admin user with a 'member' membership must keep platform_admin."""
        from src.models.models import User, Membership, Organization
        from src.models.enums import RoleType
        from src.security.tokens import decode_token

        # Admin user already exists (bootstrapped as platform_admin)
        admin = User.query.filter_by(username="admin").first()
        assert admin.role == RoleType.PLATFORM_ADMIN.value

        # Create org + give admin a 'member' membership
        org = Organization(name="AdminMember Org", slug=f"admem-{uuid.uuid4().hex[:6]}")
        db.session.add(org)
        db.session.flush()
        membership = Membership(
            user_id=admin.id,
            organization_id=org.id,
            role=RoleType.MEMBER.value,
            is_active=True,
        )
        db.session.add(membership)
        db.session.commit()

        login_resp = client.post("/auth/login", json={
            "username": "admin",
            "password": "admin",
        })
        assert login_resp.status_code == 200
        token = login_resp.get_json()["data"]["access_token"]
        payload = decode_token(token)

        # Should still be platform_admin (not downgraded to member)
        assert payload["role"] == RoleType.PLATFORM_ADMIN.value


class TestSwitchContextReissuesTokens:
    """switch-context must re-issue tokens with the target org's membership role."""

    def test_switch_context_returns_new_tokens(self, client, db):
        """After switch-context, the response must include new access and refresh tokens."""
        from src.models.models import User, Membership, Organization
        from src.models.enums import RoleType
        from src.security.tokens import decode_token

        username = f"switch_{uuid.uuid4().hex[:8]}"
        reg_resp = client.post("/auth/register-guest", json={
            "username": username,
            "password": "SecurePass1!",
        })
        user_id = reg_resp.get_json()["data"]["user"]["id"]

        # Create two orgs with different roles
        org_a = Organization(name="Org A", slug=f"orga-{uuid.uuid4().hex[:6]}")
        org_b = Organization(name="Org B", slug=f"orgb-{uuid.uuid4().hex[:6]}")
        db.session.add_all([org_a, org_b])
        db.session.flush()

        m_a = Membership(user_id=user_id, organization_id=org_a.id, role=RoleType.MEMBER.value)
        m_b = Membership(user_id=user_id, organization_id=org_b.id, role=RoleType.ORG_ADMIN.value)
        db.session.add_all([m_a, m_b])
        db.session.commit()

        # Login (picks first membership — org A, member)
        login_resp = client.post("/auth/login", json={
            "username": username,
            "password": "SecurePass1!",
        })
        token_a = login_resp.get_json()["data"]["access_token"]
        headers_a = {"Authorization": f"Bearer {token_a}"}

        # Switch to org B
        switch_resp = client.post("/permissions/memberships/switch-context", json={
            "organization_id": org_b.id,
        }, headers=headers_a)
        assert switch_resp.status_code == 200
        data = switch_resp.get_json()["data"]

        # Must have new tokens
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["organization_id"] == org_b.id

        # New token should have org_admin role for org B
        new_payload = decode_token(data["access_token"])
        assert new_payload["role"] == RoleType.ORG_ADMIN.value
        assert new_payload["org_id"] == org_b.id


class TestInvitationRedemptionReissuesTokens:
    """Invitation redemption must re-issue tokens with the new membership role."""

    def test_redeem_returns_new_tokens(self, client, admin_headers, org_setup, db):
        """After redeeming an invitation, new tokens must be returned."""
        from src.security.tokens import decode_token

        # Create invitation (admin creates it)
        inv_resp = client.post("/invitations", json={
            "organization_id": org_setup["id"],
            "target_role": "member",
        }, headers=admin_headers)
        assert inv_resp.status_code == 201
        code = inv_resp.get_json()["data"]["code"]

        # Register a fresh guest
        username = f"redinv_{uuid.uuid4().hex[:8]}"
        reg_resp = client.post("/auth/register-guest", json={
            "username": username,
            "password": "SecurePass1!",
        })
        guest_token = reg_resp.get_json()["data"]["access_token"]
        guest_headers = {"Authorization": f"Bearer {guest_token}"}

        # Redeem invitation
        redeem_resp = client.post("/invitations/redeem", json={
            "code": code,
        }, headers=guest_headers)
        assert redeem_resp.status_code == 200
        data = redeem_resp.get_json()["data"]

        # Must have new tokens
        assert "access_token" in data
        assert "refresh_token" in data

        # New token must have the membership role and org context
        new_payload = decode_token(data["access_token"])
        assert new_payload["role"] == "member"
        assert new_payload["org_id"] == org_setup["id"]

    def test_redeem_org_admin_invitation_grants_org_admin_token(self, client, admin_headers, org_setup, db):
        """Redeeming an org_admin invitation must yield an org_admin token."""
        from src.security.tokens import decode_token

        inv_resp = client.post("/invitations", json={
            "organization_id": org_setup["id"],
            "target_role": "org_admin",
        }, headers=admin_headers)
        code = inv_resp.get_json()["data"]["code"]

        username = f"redadm_{uuid.uuid4().hex[:8]}"
        reg_resp = client.post("/auth/register-guest", json={
            "username": username,
            "password": "SecurePass1!",
        })
        guest_token = reg_resp.get_json()["data"]["access_token"]

        redeem_resp = client.post("/invitations/redeem", json={
            "code": code,
        }, headers={"Authorization": f"Bearer {guest_token}"})
        assert redeem_resp.status_code == 200
        data = redeem_resp.get_json()["data"]

        new_payload = decode_token(data["access_token"])
        assert new_payload["role"] == "org_admin"


class TestRequireRoleDBVerification:
    """require_role must verify role against DB membership, not just JWT."""

    def test_require_role_checks_membership_from_db(self, client, db):
        """If a membership role is downgraded in the DB after token issuance,
        require_role should enforce the DB state."""
        from src.models.models import User, Membership, Organization
        from src.models.enums import RoleType

        username = f"dbcheck_{uuid.uuid4().hex[:8]}"
        reg_resp = client.post("/auth/register-guest", json={
            "username": username,
            "password": "SecurePass1!",
        })
        user_id = reg_resp.get_json()["data"]["user"]["id"]

        org = Organization(name="DBCheck Org", slug=f"dbchk-{uuid.uuid4().hex[:6]}")
        db.session.add(org)
        db.session.flush()

        # Give org_admin membership
        membership = Membership(
            user_id=user_id,
            organization_id=org.id,
            role=RoleType.ORG_ADMIN.value,
        )
        db.session.add(membership)
        db.session.commit()

        # Login — gets org_admin token
        login_resp = client.post("/auth/login", json={
            "username": username,
            "password": "SecurePass1!",
        })
        token = login_resp.get_json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Now downgrade the membership in the DB to member
        membership.role = RoleType.MEMBER.value
        db.session.commit()

        # Try to access an org_admin-only endpoint (e.g., create invitation)
        resp = client.post("/invitations", json={
            "organization_id": org.id,
            "target_role": "member",
        }, headers=headers)
        # Should be forbidden because DB role is now 'member'
        assert resp.status_code == 403

    def test_platform_admin_bypasses_membership_downgrade(self, client, db):
        """A platform_admin global role should bypass any membership role downgrade."""
        from src.models.models import User, Membership, Organization
        from src.models.enums import RoleType

        admin = User.query.filter_by(username="admin").first()

        org = Organization(name="AdminBypass Org", slug=f"bypass-{uuid.uuid4().hex[:6]}")
        db.session.add(org)
        db.session.flush()

        # Give admin a 'guest' membership (lowest possible)
        membership = Membership(
            user_id=admin.id,
            organization_id=org.id,
            role=RoleType.GUEST.value,
        )
        db.session.add(membership)
        db.session.commit()

        login_resp = client.post("/auth/login", json={
            "username": "admin",
            "password": "admin",
        })
        token = login_resp.get_json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Admin should still be able to access platform_admin endpoints
        resp = client.get("/admin/system-status", headers=headers)
        assert resp.status_code == 200


class TestDeviceBlacklistCooldown:
    """Device blacklisting must use blacklisted_until for time-based cooldown."""

    def test_device_model_has_blacklisted_until(self, client, db):
        """Device model must have blacklisted_until column."""
        from src.models.models import Device
        assert hasattr(Device, "blacklisted_until")

    def test_blacklisted_device_blocks_login(self, client, db):
        """A device with blacklisted status and future blacklisted_until blocks login."""
        from src.models.models import Device, User
        from src.models.enums import DeviceStatus
        from src.security.encryption import encrypt_field, compute_fingerprint_lookup_hash
        from src.config import config

        username = f"bldev_{uuid.uuid4().hex[:8]}"
        client.post("/auth/register-guest", json={
            "username": username,
            "password": "SecurePass1!",
        })
        user = User.query.filter_by(username=username).first()

        fingerprint = f"blocked-fp-{uuid.uuid4().hex}"
        fp_encrypted = encrypt_field(fingerprint, config.ENCRYPTION_MASTER_KEY, "device_fingerprint")
        fp_lookup = compute_fingerprint_lookup_hash(fingerprint)

        device = Device(
            user_id=user.id,
            fingerprint_hash=fp_encrypted,
            fingerprint_lookup_hash=fp_lookup,
            status=DeviceStatus.BLACKLISTED.value,
            blacklisted_until=datetime.now(timezone.utc) + timedelta(hours=24),
            risk_score=0.95,
        )
        db.session.add(device)
        db.session.commit()

        resp = client.post("/auth/login", json={
            "username": username,
            "password": "SecurePass1!",
            "device_fingerprint": fingerprint,
        })
        assert resp.status_code == 403
        assert resp.get_json()["error"]["code"] == "DEVICE_BLACKLISTED"
        assert resp.get_json()["error"]["details"]["retry_after"] > 0

    def test_expired_blacklist_allows_login(self, client, db):
        """A device whose blacklisted_until is in the past should be reactivated."""
        from src.models.models import Device, User
        from src.models.enums import DeviceStatus
        from src.security.encryption import encrypt_field, compute_fingerprint_lookup_hash
        from src.config import config

        username = f"expbl_{uuid.uuid4().hex[:8]}"
        client.post("/auth/register-guest", json={
            "username": username,
            "password": "SecurePass1!",
        })
        user = User.query.filter_by(username=username).first()

        fingerprint = f"expired-fp-{uuid.uuid4().hex}"
        fp_encrypted = encrypt_field(fingerprint, config.ENCRYPTION_MASTER_KEY, "device_fingerprint")
        fp_lookup = compute_fingerprint_lookup_hash(fingerprint)

        device = Device(
            user_id=user.id,
            fingerprint_hash=fp_encrypted,
            fingerprint_lookup_hash=fp_lookup,
            status=DeviceStatus.BLACKLISTED.value,
            blacklisted_until=datetime.now(timezone.utc) - timedelta(hours=1),
            risk_score=0.95,
        )
        db.session.add(device)
        db.session.commit()

        resp = client.post("/auth/login", json={
            "username": username,
            "password": "SecurePass1!",
            "device_fingerprint": fingerprint,
        })
        # Should NOT be blocked — cooldown expired
        assert resp.status_code == 200

        # Device should have been reactivated
        db.session.refresh(device)
        assert device.status == DeviceStatus.ACTIVE.value
        assert device.blacklisted_until is None


class TestContentRecommendations:
    """Recommendation endpoint must exist with proper exclusion logic."""

    def _create_content(self, client, headers, org_id, title, body="Some content body."):
        resp = client.post("/content", json={
            "title": title,
            "body": body,
            "organization_id": org_id,
        }, headers=headers)
        assert resp.status_code == 201
        return resp.get_json()["data"]

    def _create_other_user_with_content(self, client, db, org_id):
        """Create a second user in the org who creates content."""
        from src.models.models import Membership
        from src.models.enums import RoleType

        username = f"author_{uuid.uuid4().hex[:8]}"
        reg_resp = client.post("/auth/register-guest", json={
            "username": username,
            "password": "SecurePass1!",
        })
        user_id = reg_resp.get_json()["data"]["user"]["id"]

        m = Membership(user_id=user_id, organization_id=org_id, role=RoleType.MEMBER.value)
        db.session.add(m)
        db.session.commit()

        login_resp = client.post("/auth/login", json={
            "username": username,
            "password": "SecurePass1!",
        })
        token = login_resp.get_json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        return user_id, headers

    def test_recommendations_endpoint_exists(self, client, member_user, org_setup, db):
        resp = client.get(
            f"/content/recommendations?organization_id={org_setup['id']}",
            headers=member_user["headers"],
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert "data" in body
        assert "pagination" in body

    def test_excludes_own_content(self, client, member_user, org_setup, db):
        """Content created by the requesting user should not appear in recommendations."""
        author_id, author_headers = self._create_other_user_with_content(client, db, org_setup["id"])

        # Author creates content
        other_content = self._create_content(client, author_headers, org_setup["id"], "Other Author Article")

        # Member creates own content
        own_content = self._create_content(client, member_user["headers"], org_setup["id"], "My Own Article")

        resp = client.get(
            f"/content/recommendations?organization_id={org_setup['id']}",
            headers=member_user["headers"],
        )
        assert resp.status_code == 200
        ids = [item["id"] for item in resp.get_json()["data"]]
        assert other_content["id"] in ids
        assert own_content["id"] not in ids

    def test_excludes_suppressed_content(self, client, member_user, org_setup, db):
        """SUPPRESSED content must not appear in recommendations."""
        from src.models.models import ContentItem
        from src.models.enums import ContentQualityState

        author_id, author_headers = self._create_other_user_with_content(client, db, org_setup["id"])
        content = self._create_content(client, author_headers, org_setup["id"], "Suppressed Article")

        # Suppress it directly in DB
        item = ContentItem.query.get(content["id"])
        item.quality_state = ContentQualityState.SUPPRESSED.value
        db.session.commit()

        resp = client.get(
            f"/content/recommendations?organization_id={org_setup['id']}",
            headers=member_user["headers"],
        )
        ids = [item["id"] for item in resp.get_json()["data"]]
        assert content["id"] not in ids

    def test_excludes_demoted_content(self, client, member_user, org_setup, db):
        """DUPLICATE_DEMOTED and RATING_DEMOTED content must not appear."""
        from src.models.models import ContentItem
        from src.models.enums import ContentQualityState

        author_id, author_headers = self._create_other_user_with_content(client, db, org_setup["id"])

        dup_content = self._create_content(client, author_headers, org_setup["id"], "Dup Article")
        rating_content = self._create_content(client, author_headers, org_setup["id"], "LowRate Article")

        ContentItem.query.get(dup_content["id"]).quality_state = ContentQualityState.DUPLICATE_DEMOTED.value
        ContentItem.query.get(rating_content["id"]).quality_state = ContentQualityState.RATING_DEMOTED.value
        db.session.commit()

        resp = client.get(
            f"/content/recommendations?organization_id={org_setup['id']}",
            headers=member_user["headers"],
        )
        ids = [item["id"] for item in resp.get_json()["data"]]
        assert dup_content["id"] not in ids
        assert rating_content["id"] not in ids

    def test_excludes_already_rated_content(self, client, member_user, org_setup, db):
        """Content the user has already rated should be excluded."""
        author_id, author_headers = self._create_other_user_with_content(client, db, org_setup["id"])
        content = self._create_content(client, author_headers, org_setup["id"], "Already Rated Article")

        # Rate it
        client.post(f"/content/{content['id']}/ratings", json={
            "score": 4,
        }, headers=member_user["headers"])

        resp = client.get(
            f"/content/recommendations?organization_id={org_setup['id']}",
            headers=member_user["headers"],
        )
        ids = [item["id"] for item in resp.get_json()["data"]]
        assert content["id"] not in ids

    def test_excludes_already_favorited_content(self, client, member_user, org_setup, db):
        """Content the user has favorited should be excluded."""
        author_id, author_headers = self._create_other_user_with_content(client, db, org_setup["id"])
        content = self._create_content(client, author_headers, org_setup["id"], "Already Fav Article")

        client.post(f"/content/{content['id']}/favorite", headers=member_user["headers"])

        resp = client.get(
            f"/content/recommendations?organization_id={org_setup['id']}",
            headers=member_user["headers"],
        )
        ids = [item["id"] for item in resp.get_json()["data"]]
        assert content["id"] not in ids

    def test_excludes_already_downloaded_content(self, client, member_user, org_setup, db):
        """Content the user has downloaded should be excluded."""
        author_id, author_headers = self._create_other_user_with_content(client, db, org_setup["id"])
        content = self._create_content(client, author_headers, org_setup["id"], "Already DL Article")

        client.post(f"/content/{content['id']}/download", headers=member_user["headers"])

        resp = client.get(
            f"/content/recommendations?organization_id={org_setup['id']}",
            headers=member_user["headers"],
        )
        ids = [item["id"] for item in resp.get_json()["data"]]
        assert content["id"] not in ids

    def test_recommendations_ordered_by_rating(self, client, member_user, org_setup, db):
        """Recommendations should be ordered by avg_rating descending."""
        from src.models.models import ContentItem

        author_id, author_headers = self._create_other_user_with_content(client, db, org_setup["id"])

        low = self._create_content(client, author_headers, org_setup["id"], "Low Rated Rec")
        high = self._create_content(client, author_headers, org_setup["id"], "High Rated Rec")

        ContentItem.query.get(low["id"]).avg_rating = 1.0
        ContentItem.query.get(high["id"]).avg_rating = 5.0
        db.session.commit()

        resp = client.get(
            f"/content/recommendations?organization_id={org_setup['id']}",
            headers=member_user["headers"],
        )
        items = resp.get_json()["data"]
        # High-rated should come before low-rated
        ids = [item["id"] for item in items]
        if high["id"] in ids and low["id"] in ids:
            assert ids.index(high["id"]) < ids.index(low["id"])

    def test_requires_org_context(self, client, db):
        """Recommendations without org context should fail."""
        username = f"noorg_{uuid.uuid4().hex[:8]}"
        reg_resp = client.post("/auth/register-guest", json={
            "username": username,
            "password": "SecurePass1!",
        })
        token = reg_resp.get_json()["data"]["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        resp = client.get("/content/recommendations", headers=headers)
        assert resp.status_code == 403


class TestReservationOrgBinding:
    """Hold endpoint must verify resource-org match and caller membership."""

    def test_hold_rejects_mismatched_org(self, client, member_user, org_setup, db):
        """Caller cannot create a hold with an organization_id that doesn't match the resource."""
        from src.models.models import Resource, Organization

        # Create a resource in the test org
        resource = Resource(
            organization_id=org_setup["id"],
            name="Bound Resource",
            capacity=1,
        )
        db.session.add(resource)

        # Create a different org
        other_org = Organization(name="Other Org", slug=f"other-{uuid.uuid4().hex[:6]}")
        db.session.add(other_org)
        db.session.commit()

        resp = client.post("/reservations/hold", json={
            "resource_id": resource.id,
            "organization_id": other_org.id,
            "start_time": "2099-06-01T10:00:00+00:00",
            "end_time": "2099-06-01T11:00:00+00:00",
        }, headers={
            **member_user["headers"],
            "Idempotency-Key": uuid.uuid4().hex,
        })
        assert resp.status_code == 400
        assert "does not belong" in resp.get_json()["error"]["message"]

    def test_hold_rejects_non_member_org(self, client, db, org_setup):
        """A user without membership in the org cannot create holds there."""
        from src.models.models import Resource, Organization

        # Create resource
        resource = Resource(
            organization_id=org_setup["id"],
            name="Auth Resource",
            capacity=1,
        )
        db.session.add(resource)
        db.session.commit()

        # Register a user with NO membership in org_setup
        username = f"noorg_{uuid.uuid4().hex[:8]}"
        reg_resp = client.post("/auth/register-guest", json={
            "username": username,
            "password": "SecurePass1!",
        })
        token = reg_resp.get_json()["data"]["access_token"]
        headers = {
            "Authorization": f"Bearer {token}",
            "Idempotency-Key": uuid.uuid4().hex,
        }

        resp = client.post("/reservations/hold", json={
            "resource_id": resource.id,
            "organization_id": org_setup["id"],
            "start_time": "2099-06-01T10:00:00+00:00",
            "end_time": "2099-06-01T11:00:00+00:00",
        }, headers=headers)
        assert resp.status_code == 403


class TestAuditNoteRedaction:
    """Moderation notes must not leak through audit event payloads."""

    def test_moderation_decision_audit_redacts_notes(self, client, member_user, org_setup, db):
        """decision_notes in audit after_state must be [REDACTED]."""
        from src.models.models import ContentItem, ModerationCase, AuditEvent
        from src.models.enums import AuditEventType
        import json

        # Create content, report it, suppress it
        resp = client.post("/content", json={
            "title": "Audit Leak Test",
            "body": "Content body for audit leak test.",
            "organization_id": org_setup["id"],
        }, headers=member_user["headers"])
        content_id = resp.get_json()["data"]["id"]

        report_resp = client.post(f"/content/{content_id}/report", json={
            "reason": "Testing audit redaction.",
        }, headers=member_user["headers"])
        case_id = report_resp.get_json()["data"]["id"]

        # Get admin with moderation permission
        from src.models.models import Permission, UserPermission, User
        perm = Permission.query.filter_by(code="moderation:review").first()
        if not perm:
            perm = Permission(code="moderation:review", description="Can moderate")
            db.session.add(perm)
            db.session.flush()
        admin = User.query.filter_by(username="admin").first()
        if not UserPermission.query.filter_by(user_id=admin.id, permission_id=perm.id).first():
            db.session.add(UserPermission(user_id=admin.id, permission_id=perm.id))
            db.session.commit()

        login_resp = client.post("/auth/login", json={
            "username": "admin", "password": "admin",
        })
        mod_headers = {"Authorization": f"Bearer {login_resp.get_json()['data']['access_token']}"}

        client.post(f"/moderation/cases/{case_id}/decision", json={
            "action": "SUPPRESS",
            "decision_notes": "SENSITIVE: This is a secret moderation note.",
        }, headers=mod_headers)

        # Check the audit event — decision_notes should be redacted
        audit = AuditEvent.query.filter_by(
            event_type=AuditEventType.MODERATION_DECISION.value,
            target_id=case_id,
        ).first()
        assert audit is not None
        after = json.loads(audit.after_state)
        assert after["decision_notes"] == "[REDACTED]"

    def test_audit_endpoint_redacts_notes(self, client, db, admin_headers):
        """The /audit-events endpoint must also redact notes in responses."""
        from src.api.audit import _redact_state_json
        import json

        raw = json.dumps({"case_action": "SUPPRESS", "decision_notes": "secret stuff"})
        result = _redact_state_json(raw)
        data = json.loads(result)
        assert data["decision_notes"] == "[REDACTED]"
        assert data["case_action"] == "SUPPRESS"


class TestOverlapTrigger:
    """DB-level trigger must reject overlapping reservations."""

    def test_trigger_prevents_overlap(self, client, member_user, org_setup, db):
        """Two holds with overlapping time ranges should not both succeed."""
        from src.models.models import Resource

        resource = Resource(
            organization_id=org_setup["id"],
            name="Trigger Resource",
            capacity=1,
        )
        db.session.add(resource)
        db.session.commit()

        # First hold
        resp1 = client.post("/reservations/hold", json={
            "resource_id": resource.id,
            "organization_id": org_setup["id"],
            "start_time": "2099-07-01T10:00:00+00:00",
            "end_time": "2099-07-01T11:00:00+00:00",
        }, headers={
            **member_user["headers"],
            "Idempotency-Key": uuid.uuid4().hex,
        })
        assert resp1.status_code == 201

        # Overlapping hold (partial overlap)
        resp2 = client.post("/reservations/hold", json={
            "resource_id": resource.id,
            "organization_id": org_setup["id"],
            "start_time": "2099-07-01T10:30:00+00:00",
            "end_time": "2099-07-01T11:30:00+00:00",
        }, headers={
            **member_user["headers"],
            "Idempotency-Key": uuid.uuid4().hex,
        })
        assert resp2.status_code == 409


class TestEncryptedHashStorage:
    """Password hash and token hash must be encrypted at rest."""

    def test_password_hash_column_is_encrypted(self, db):
        """The User.password_hash column should use EncryptedText type."""
        from src.models.models import User, EncryptedText
        col_type = User.__table__.columns["password_hash"].type
        assert isinstance(col_type, EncryptedText)

    def test_token_hash_uses_keyed_hmac(self):
        """hash_token must produce different output than plain SHA-256."""
        import hashlib
        from src.security.tokens import hash_token

        test_token = "test-token-value-12345"
        plain_sha = hashlib.sha256(test_token.encode("utf-8")).hexdigest()
        keyed_hash = hash_token(test_token)

        # Keyed HMAC should differ from plain SHA-256
        assert keyed_hash != plain_sha
        # But same token should produce same keyed hash (deterministic)
        assert hash_token(test_token) == keyed_hash

    def test_password_roundtrip_works(self, client, db):
        """Register and login must still work with encrypted password_hash."""
        username = f"encpw_{uuid.uuid4().hex[:8]}"
        reg_resp = client.post("/auth/register-guest", json={
            "username": username,
            "password": "SecurePass1!",
        })
        assert reg_resp.status_code == 201

        login_resp = client.post("/auth/login", json={
            "username": username,
            "password": "SecurePass1!",
        })
        assert login_resp.status_code == 200

    def test_refresh_token_roundtrip_works(self, client, db):
        """Token refresh must still work with keyed HMAC token hashing."""
        username = f"encrt_{uuid.uuid4().hex[:8]}"
        client.post("/auth/register-guest", json={
            "username": username,
            "password": "SecurePass1!",
        })
        login_resp = client.post("/auth/login", json={
            "username": username,
            "password": "SecurePass1!",
        })
        refresh_token = login_resp.get_json()["data"]["refresh_token"]

        refresh_resp = client.post("/auth/refresh", json={
            "refresh_token": refresh_token,
        })
        assert refresh_resp.status_code == 200
        assert "access_token" in refresh_resp.get_json()["data"]


class TestDataModelParityAPI:
    """Prompt-specified model fields must be exposed in API responses."""

    def test_permission_fields_in_api_response(self, client, admin_headers, db):
        """Permission API must expose action/category/assignable fields."""
        code = f"model.parity.{uuid.uuid4().hex[:6]}"
        resp = client.post("/permissions", json={
            "code": code,
            "description": "Parity test",
            "action": "read",
            "category": "content",
            "assignable": True,
        }, headers=admin_headers)
        assert resp.status_code == 201
        data = resp.get_json()["data"]
        assert data["action"] == "read"
        assert data["category"] == "content"
        assert data["assignable"] is True

    def test_content_item_suppressed_until_in_response(self, client, member_user, org_setup, db):
        """Content serializer must include suppressed_until field."""
        resp = client.post("/content", json={
            "title": "Suppressed Until Test",
            "body": "Body content.",
            "organization_id": org_setup["id"],
        }, headers=member_user["headers"])
        assert resp.status_code == 201
        data = resp.get_json()["data"]
        assert "suppressed_until" in data
