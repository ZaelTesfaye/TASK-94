"""Unit tests for enum definitions and state machine constants."""
import pytest

from src.models.enums import (
    RoleType,
    ROLE_HIERARCHY,
    ReservationStatus,
    RESERVATION_TRANSITIONS,
    DifficultyBucket,
    DIFFICULTY_THRESHOLDS,
)


def test_role_hierarchy_ordering():
    """GUEST < MEMBER < ORG_ADMIN < PLATFORM_ADMIN in the hierarchy."""
    assert ROLE_HIERARCHY[RoleType.GUEST] < ROLE_HIERARCHY[RoleType.MEMBER]
    assert ROLE_HIERARCHY[RoleType.MEMBER] < ROLE_HIERARCHY[RoleType.ORG_ADMIN]
    assert ROLE_HIERARCHY[RoleType.ORG_ADMIN] < ROLE_HIERARCHY[RoleType.PLATFORM_ADMIN]


def test_reservation_transitions_held():
    """HELD can transition to CONFIRMED, CANCELLED, RELEASED."""
    allowed = RESERVATION_TRANSITIONS[ReservationStatus.HELD]
    assert ReservationStatus.CONFIRMED in allowed
    assert ReservationStatus.CANCELLED in allowed
    assert ReservationStatus.RELEASED in allowed


def test_reservation_transitions_confirmed():
    """CONFIRMED can transition to CANCELLED and RESCHEDULED."""
    allowed = RESERVATION_TRANSITIONS[ReservationStatus.CONFIRMED]
    assert ReservationStatus.CANCELLED in allowed
    assert ReservationStatus.RESCHEDULED in allowed


def test_reservation_transitions_terminal():
    """CANCELLED, RELEASED, and RESCHEDULED are terminal (no transitions)."""
    assert RESERVATION_TRANSITIONS[ReservationStatus.CANCELLED] == set()
    assert RESERVATION_TRANSITIONS[ReservationStatus.RELEASED] == set()
    assert RESERVATION_TRANSITIONS[ReservationStatus.RESCHEDULED] == set()


def test_difficulty_thresholds_coverage():
    """DIFFICULTY_THRESHOLDS should cover the full 0-1 range.

    The lowest threshold must be 0.0 (catches everything) and the highest
    must be < 1.0 (so that a perfect score still maps to a bucket).
    """
    thresholds_sorted = sorted(DIFFICULTY_THRESHOLDS, key=lambda t: t[0])
    # The lowest boundary must be 0.0 to cover values near zero
    assert thresholds_sorted[0][0] == 0.0
    # The highest boundary must be less than or equal to 1.0
    assert thresholds_sorted[-1][0] <= 1.0
    # All four buckets are represented
    buckets_in_thresholds = {bucket for _, bucket in DIFFICULTY_THRESHOLDS}
    assert buckets_in_thresholds == {
        DifficultyBucket.EASY,
        DifficultyBucket.MEDIUM,
        DifficultyBucket.HARD,
        DifficultyBucket.VERY_HARD,
    }
