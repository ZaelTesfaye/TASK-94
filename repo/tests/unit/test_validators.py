"""Unit tests for input validation utilities."""
import pytest
import uuid

from src.utils.validators import (
    validate_required,
    validate_string,
    validate_uuid,
    validate_enum,
)
from src.models.enums import RoleType


def test_validate_required_missing_field():
    """Should return an error when a required field is missing."""
    errors = validate_required({"name": "Alice"}, ["name", "email"])
    assert len(errors) == 1
    assert "email" in errors[0].lower()


def test_validate_required_all_present():
    """Should return an empty list when all required fields are present."""
    errors = validate_required({"name": "Alice", "email": "a@b.com"}, ["name", "email"])
    assert errors == []


def test_validate_string_too_short():
    """Should return an error when string is shorter than min_len."""
    errors = validate_string("ab", "username", min_len=3)
    assert len(errors) == 1
    assert "at least 3" in errors[0]


def test_validate_string_valid():
    """Should return an empty list for a valid string within constraints."""
    errors = validate_string("hello", "greeting", min_len=1, max_len=10)
    assert errors == []


def test_validate_uuid_valid():
    """A valid UUID string should pass validation."""
    valid = str(uuid.uuid4())
    errors = validate_uuid(valid, "id")
    assert errors == []


def test_validate_uuid_invalid():
    """A garbage string should fail UUID validation."""
    errors = validate_uuid("not-a-uuid", "id")
    assert len(errors) == 1
    assert "uuid" in errors[0].lower()


def test_validate_enum_valid():
    """A valid enum value should pass validation."""
    errors = validate_enum(RoleType.MEMBER.value, "role", RoleType)
    assert errors == []


def test_validate_enum_invalid():
    """An invalid value should fail enum validation."""
    errors = validate_enum("superadmin", "role", RoleType)
    assert len(errors) == 1
    assert "must be one of" in errors[0].lower()
