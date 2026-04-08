"""JWT access/refresh token service - plan section 7 security controls."""

import hashlib
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt

from src.config import config
from src.logging import logger


def create_access_token(
    user_id: str,
    username: str,
    role: str,
    organization_id: str = None,
    permissions: list = None,
) -> str:
    """Create a JWT access token with user claims.

    Args:
        user_id: The user's unique identifier.
        username: The user's username.
        role: The user's role.
        organization_id: Optional organization context.
        permissions: Optional list of permission codes.

    Returns:
        Encoded JWT string.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "org_id": organization_id,
        "permissions": permissions or [],
        "jti": str(uuid4()),
        "iat": now,
        "exp": now + timedelta(minutes=config.JWT_ACCESS_TOKEN_EXPIRES_MINUTES),
        "iss": config.JWT_ISSUER,
    }
    token = jwt.encode(payload, config.JWT_SECRET_KEY, algorithm=config.JWT_ALGORITHM)
    logger.info("security", "tokens", f"Access token created for user={user_id}")
    return token


def create_refresh_token(user_id: str) -> str:
    """Create a JWT refresh token.

    Args:
        user_id: The user's unique identifier.

    Returns:
        Encoded JWT refresh token string.
    """
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "jti": str(uuid4()),
        "type": "refresh",
        "iat": now,
        "exp": now + timedelta(days=config.JWT_REFRESH_TOKEN_EXPIRES_DAYS),
        "iss": config.JWT_ISSUER,
    }
    token = jwt.encode(payload, config.JWT_SECRET_KEY, algorithm=config.JWT_ALGORITHM)
    logger.info("security", "tokens", f"Refresh token created for user={user_id}")
    return token


def decode_token(token: str) -> dict | None:
    """Decode and validate a JWT token.

    Args:
        token: The encoded JWT string.

    Returns:
        The decoded payload dict, or None if decoding/validation fails.
    """
    try:
        payload = jwt.decode(
            token,
            config.JWT_SECRET_KEY,
            algorithms=[config.JWT_ALGORITHM],
            issuer=config.JWT_ISSUER,
        )
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("security", "tokens", "Token has expired")
        return None
    except jwt.InvalidTokenError as exc:
        logger.warning("security", "tokens", f"Invalid token: {exc}")
        return None


def hash_token(token: str) -> str:
    """Create a SHA-256 hash of a token for safe storage.

    Args:
        token: The raw token string.

    Returns:
        Hex-encoded SHA-256 hash.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
