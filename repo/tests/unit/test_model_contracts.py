"""Unit tests for data model field contracts.

These tests verify that prompt-specified model fields are present. Moved from
tests/api/test_prompt_compliance.py because they are structural checks, not
HTTP tests.
"""

import pytest


class TestDataModelParity:
    """All prompt-specified model fields must be present."""

    def test_membership_has_data_scope(self):
        from src.models.models import Membership
        assert hasattr(Membership, "data_scope")

    def test_permission_has_action_category_assignable(self):
        from src.models.models import Permission
        assert hasattr(Permission, "action")
        assert hasattr(Permission, "category")
        assert hasattr(Permission, "assignable")

    def test_slot_template_has_timezone_and_buffer(self):
        from src.models.models import SlotTemplate
        assert hasattr(SlotTemplate, "timezone")
        assert hasattr(SlotTemplate, "buffer_minutes")

    def test_learning_event_has_duration_seconds(self):
        from src.models.models import LearningEvent
        assert hasattr(LearningEvent, "duration_seconds")

    def test_content_item_has_suppressed_until(self):
        from src.models.models import ContentItem
        assert hasattr(ContentItem, "suppressed_until")
