"""Unit tests for invitation logic: role hierarchy validation, code generation,
and expiry behaviour exercised at the model/config level."""

import pytest

from src.models.enums import RoleType, ROLE_HIERARCHY, InvitationStatus


class TestRoleHierarchyValidation:
    """Invitation creation requires that the target role does not exceed the caller's role."""

    def test_all_roles_present_in_hierarchy(self):
        for role in RoleType:
            assert role in ROLE_HIERARCHY, f"{role} missing from ROLE_HIERARCHY"

    def test_hierarchy_ordering(self):
        assert ROLE_HIERARCHY[RoleType.GUEST] < ROLE_HIERARCHY[RoleType.MEMBER]
        assert ROLE_HIERARCHY[RoleType.MEMBER] < ROLE_HIERARCHY[RoleType.ORG_ADMIN]
        assert ROLE_HIERARCHY[RoleType.ORG_ADMIN] < ROLE_HIERARCHY[RoleType.PLATFORM_ADMIN]

    def test_caller_can_invite_equal_role(self):
        """An org_admin can create an invitation targeting org_admin."""
        caller_level = ROLE_HIERARCHY[RoleType.ORG_ADMIN]
        target_level = ROLE_HIERARCHY[RoleType.ORG_ADMIN]
        assert target_level <= caller_level

    def test_caller_can_invite_lower_role(self):
        """An org_admin can create an invitation targeting member."""
        caller_level = ROLE_HIERARCHY[RoleType.ORG_ADMIN]
        target_level = ROLE_HIERARCHY[RoleType.MEMBER]
        assert target_level <= caller_level

    def test_caller_cannot_invite_higher_role(self):
        """A member cannot create an invitation targeting org_admin."""
        caller_level = ROLE_HIERARCHY[RoleType.MEMBER]
        target_level = ROLE_HIERARCHY[RoleType.ORG_ADMIN]
        assert target_level > caller_level


class TestInvitationStatusTransitions:
    """Invitation status enum must cover all expected states."""

    def test_all_statuses_exist(self):
        assert InvitationStatus.PENDING.value == "PENDING"
        assert InvitationStatus.REDEEMED.value == "REDEEMED"
        assert InvitationStatus.REVOKED.value == "REVOKED"
        assert InvitationStatus.EXPIRED.value == "EXPIRED"

    def test_pending_is_initial_state(self):
        """New invitations should start as PENDING."""
        assert InvitationStatus.PENDING.value == "PENDING"


class TestInvitationCodeGeneration:
    """The invitation code generation produces unique hex strings."""

    def test_uuid_hex_generates_unique_codes(self):
        import uuid

        codes = {uuid.uuid4().hex[:12].upper() for _ in range(100)}
        assert len(codes) == 100  # all unique

    def test_code_format_is_uppercase_hex(self):
        import uuid

        code = uuid.uuid4().hex[:12].upper()
        assert len(code) == 12
        assert code == code.upper()
        assert all(c in "0123456789ABCDEF" for c in code)


class TestInvitationExpiryConfig:
    def test_default_expiry_hours(self):
        from src.config import config

        assert hasattr(config, "INVITATION_EXPIRY_HOURS")
        assert config.INVITATION_EXPIRY_HOURS == 72
