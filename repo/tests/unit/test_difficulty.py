"""Unit tests for difficulty bucket classification."""
import pytest

from src.api.analytics import _classify_difficulty
from src.models.enums import DifficultyBucket


def test_easy_threshold():
    """correct_rate=0.85 should classify as EASY."""
    assert _classify_difficulty(0.85) == DifficultyBucket.EASY.value


def test_medium_threshold():
    """correct_rate=0.65 should classify as MEDIUM."""
    assert _classify_difficulty(0.65) == DifficultyBucket.MEDIUM.value


def test_hard_threshold():
    """correct_rate=0.35 should classify as HARD."""
    assert _classify_difficulty(0.35) == DifficultyBucket.HARD.value


def test_very_hard_threshold():
    """correct_rate=0.15 should classify as VERY_HARD."""
    assert _classify_difficulty(0.15) == DifficultyBucket.VERY_HARD.value


def test_boundary_80_is_easy():
    """correct_rate=0.8 (exact boundary) should classify as EASY."""
    assert _classify_difficulty(0.8) == DifficultyBucket.EASY.value


def test_boundary_50_is_medium():
    """correct_rate=0.5 (exact boundary) should classify as MEDIUM."""
    assert _classify_difficulty(0.5) == DifficultyBucket.MEDIUM.value


def test_boundary_20_is_hard():
    """correct_rate=0.2 (exact boundary) should classify as HARD."""
    assert _classify_difficulty(0.2) == DifficultyBucket.HARD.value
