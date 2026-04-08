"""Unit tests for content fingerprint normalization."""
import pytest

from src.api.content import _normalize_fingerprint


def test_normalize_lowercase():
    """Normalization should be case-insensitive."""
    assert _normalize_fingerprint("HELLO", "WORLD") == _normalize_fingerprint("hello", "world")


def test_normalize_strips_punctuation():
    """Normalization should remove punctuation so punctuated and plain versions match."""
    fp_with = _normalize_fingerprint("Hello, World!", "Test... content.")
    fp_without = _normalize_fingerprint("Hello World", "Test content")
    assert fp_with == fp_without


def test_normalize_strips_whitespace():
    """Extra whitespace should be collapsed so different spacing produces the same hash."""
    fp_spaced = _normalize_fingerprint("  Hello   World  ", "  test   content  ")
    fp_normal = _normalize_fingerprint("Hello World", "test content")
    assert fp_spaced == fp_normal


def test_normalize_same_content_same_hash():
    """Identical inputs should always produce the same hash (deterministic)."""
    fp1 = _normalize_fingerprint("My Title", "My Body")
    fp2 = _normalize_fingerprint("My Title", "My Body")
    assert fp1 == fp2


def test_normalize_different_content_different_hash():
    """Different content should produce different hashes."""
    fp1 = _normalize_fingerprint("Title A", "Body A")
    fp2 = _normalize_fingerprint("Title B", "Body B")
    assert fp1 != fp2
