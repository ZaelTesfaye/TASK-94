"""Unit tests for Argon2id password hashing module."""
import pytest

from src.security.passwords import hash_password, verify_password


def test_hash_password_returns_string():
    """hash_password should return a non-empty string."""
    hashed = hash_password("mysecretpassword")
    assert isinstance(hashed, str)
    assert len(hashed) > 0


def test_hash_password_different_each_time():
    """Hashing the same password twice should produce different hashes (random salt)."""
    h1 = hash_password("samepassword")
    h2 = hash_password("samepassword")
    assert h1 != h2


def test_verify_correct_password():
    """verify_password should return True for the correct password."""
    password = "correcthorsebatterystaple"
    hashed = hash_password(password)
    assert verify_password(password, hashed) is True


def test_verify_wrong_password():
    """verify_password should return False for an incorrect password."""
    hashed = hash_password("rightpassword")
    assert verify_password("wrongpassword", hashed) is False


def test_verify_invalid_hash():
    """verify_password should return False (not raise) for a garbage hash string."""
    result = verify_password("anything", "not-a-valid-argon2-hash")
    assert result is False
