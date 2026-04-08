"""Password hashing with Argon2id - plan section 7 security controls."""

from argon2 import PasswordHasher
from argon2.exceptions import (
    HashingError,
    InvalidHashError,
    VerificationError,
    VerifyMismatchError,
)

from src.logging import logger

_ph = PasswordHasher()


def hash_password(password: str) -> str:
    """Hash a password using Argon2id.

    Args:
        password: The plaintext password to hash.

    Returns:
        The Argon2id hash string.
    """
    try:
        hashed = _ph.hash(password)
        logger.debug("security", "passwords", "Password hashed successfully")
        return hashed
    except HashingError:
        logger.error("security", "passwords", "Failed to hash password")
        raise


def verify_password(password: str, hash: str) -> bool:
    """Verify a password against an Argon2id hash.

    Args:
        password: The plaintext password to verify.
        hash: The stored Argon2id hash.

    Returns:
        True if the password matches, False otherwise.
    """
    try:
        return _ph.verify(hash, password)
    except VerifyMismatchError:
        logger.debug("security", "passwords", "Password verification mismatch")
        return False
    except (InvalidHashError, VerificationError) as exc:
        logger.warning("security", "passwords", f"Password verification error: {exc}")
        return False
    except Exception as exc:
        logger.error("security", "passwords", f"Unexpected password verification error: {exc}")
        return False
