"""
Input validation utilities.
"""

import enum
import uuid
from datetime import datetime


class ValidationError(Exception):
    """Raised when one or more validation checks fail.

    Attributes:
        errors: List of human-readable error strings.
    """

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("; ".join(errors))


def validate_required(data: dict, fields: list[str]) -> list[str]:
    """Check that *data* contains non-None values for each field in *fields*.

    Returns:
        List of error messages (empty if all fields are present).
    """
    errors: list[str] = []
    for field in fields:
        if field not in data or data[field] is None:
            errors.append(f"'{field}' is required.")
    return errors


def validate_string(
    value,
    field_name: str,
    min_len: int | None = None,
    max_len: int | None = None,
) -> list[str]:
    """Validate that *value* is a string with optional length constraints.

    Returns:
        List of error messages (empty if valid).
    """
    errors: list[str] = []
    if not isinstance(value, str):
        errors.append(f"'{field_name}' must be a string.")
        return errors
    if min_len is not None and len(value) < min_len:
        errors.append(f"'{field_name}' must be at least {min_len} characters.")
    if max_len is not None and len(value) > max_len:
        errors.append(f"'{field_name}' must be at most {max_len} characters.")
    return errors


def validate_integer(
    value,
    field_name: str,
    min_val: int | None = None,
    max_val: int | None = None,
) -> list[str]:
    """Validate that *value* is an integer with optional range constraints.

    Returns:
        List of error messages (empty if valid).
    """
    errors: list[str] = []
    if not isinstance(value, int) or isinstance(value, bool):
        errors.append(f"'{field_name}' must be an integer.")
        return errors
    if min_val is not None and value < min_val:
        errors.append(f"'{field_name}' must be at least {min_val}.")
    if max_val is not None and value > max_val:
        errors.append(f"'{field_name}' must be at most {max_val}.")
    return errors


def validate_enum(value, field_name: str, enum_class) -> list[str]:
    """Validate that *value* is a valid member (by value) of *enum_class*.

    Returns:
        List of error messages (empty if valid).
    """
    errors: list[str] = []
    if not issubclass(enum_class, enum.Enum):
        errors.append(f"'{field_name}' enum_class is not a valid Enum type.")
        return errors
    valid_values = [e.value for e in enum_class]
    if value not in valid_values:
        errors.append(
            f"'{field_name}' must be one of: {', '.join(str(v) for v in valid_values)}."
        )
    return errors


def validate_uuid(value, field_name: str) -> list[str]:
    """Validate that *value* is a well-formed UUID string.

    Returns:
        List of error messages (empty if valid).
    """
    errors: list[str] = []
    try:
        uuid.UUID(str(value))
    except (ValueError, AttributeError):
        errors.append(f"'{field_name}' must be a valid UUID.")
    return errors


def validate_datetime_str(value, field_name: str) -> list[str]:
    """Validate that *value* is an ISO 8601 datetime string.

    Returns:
        List of error messages (empty if valid).
    """
    errors: list[str] = []
    if not isinstance(value, str):
        errors.append(f"'{field_name}' must be an ISO 8601 datetime string.")
        return errors
    try:
        datetime.fromisoformat(value)
    except (ValueError, TypeError):
        errors.append(f"'{field_name}' must be a valid ISO 8601 datetime string.")
    return errors
