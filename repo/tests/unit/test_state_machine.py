"""Unit tests for booking state machine and content quality states."""
import pytest

from src.models.enums import (
    ReservationStatus,
    RESERVATION_TRANSITIONS,
    ContentQualityState,
    ModerationAction,
)


def test_held_to_confirmed_valid():
    """HELD -> CONFIRMED should be an allowed transition."""
    assert ReservationStatus.CONFIRMED in RESERVATION_TRANSITIONS[ReservationStatus.HELD]


def test_confirmed_to_held_invalid():
    """CONFIRMED -> HELD should NOT be allowed (no backward transition)."""
    assert ReservationStatus.HELD not in RESERVATION_TRANSITIONS[ReservationStatus.CONFIRMED]


def test_cancelled_is_terminal():
    """CANCELLED should have no outgoing transitions."""
    assert RESERVATION_TRANSITIONS[ReservationStatus.CANCELLED] == set()


def test_content_quality_states_exist():
    """All 6 ContentQualityState members should exist."""
    expected = {
        "ACTIVE", "DUPLICATE_DEMOTED", "RATING_DEMOTED",
        "REPORTED", "SUPPRESSED", "REINSTATED",
    }
    actual = {member.name for member in ContentQualityState}
    assert actual == expected


def test_moderation_actions_exist():
    """All 7 ModerationAction members should exist."""
    expected = {
        "REPORT", "REVIEW", "SUPPRESS", "REINSTATE",
        "APPEAL", "APPEAL_APPROVED", "APPEAL_DENIED",
    }
    actual = {member.name for member in ModerationAction}
    assert actual == expected
