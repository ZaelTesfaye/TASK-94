"""Request signing and anti-replay protection - plan section 7 security controls."""

import hashlib
import hmac
from datetime import datetime, timedelta, timezone

from src.config import config
from src.logging import logger
from src.models.base import db
from src.models.models import NonceStore


def verify_request_signature(request) -> tuple:
    """Verify the signature, timestamp, and nonce of an incoming request.

    Expects headers:
        X-Timestamp: ISO 8601 timestamp of when the request was signed.
        X-Nonce: Unique nonce to prevent replay attacks.
        X-Signature: HMAC-SHA256 hex digest of "method:path:timestamp:nonce:body_hash".

    Args:
        request: The Flask request object.

    Returns:
        Tuple of (is_valid: bool, error_code: str or None).
        Error codes: MISSING_SIGNATURE_HEADERS, TIMESTAMP_EXPIRED,
                     NONCE_REPLAYED, INVALID_SIGNATURE.
    """
    timestamp = request.headers.get("X-Timestamp")
    nonce = request.headers.get("X-Nonce")
    signature = request.headers.get("X-Signature")

    if not timestamp or not nonce or not signature:
        logger.warning("security", "signing", "Missing signature headers")
        return False, "MISSING_SIGNATURE_HEADERS"

    # Check timestamp skew
    try:
        request_time = datetime.fromisoformat(timestamp)
        if request_time.tzinfo is None:
            request_time = request_time.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        logger.warning("security", "signing", f"Invalid timestamp format: {timestamp}")
        return False, "TIMESTAMP_EXPIRED"

    now = datetime.now(timezone.utc)
    skew = timedelta(seconds=config.REQUEST_SIGNING_SKEW_SECONDS)
    if abs(now - request_time) > skew:
        logger.warning("security", "signing", "Request timestamp outside allowed skew")
        return False, "TIMESTAMP_EXPIRED"

    # Check nonce replay
    existing_nonce = NonceStore.query.filter_by(nonce=nonce).first()
    if existing_nonce:
        logger.warning("security", "signing", f"Nonce replayed: {nonce}")
        return False, "NONCE_REPLAYED"

    # Compute expected signature
    body = request.get_data()
    body_hash = hashlib.sha256(body).hexdigest()
    method = request.method.upper()
    path = request.path

    message = f"{method}:{path}:{timestamp}:{nonce}:{body_hash}"
    expected = hmac.new(
        config.REQUEST_SIGNING_SECRET.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        logger.warning("security", "signing", "Invalid request signature")
        return False, "INVALID_SIGNATURE"

    # Store nonce to prevent replay
    nonce_record = NonceStore(
        nonce=nonce,
        expires_at=now + timedelta(seconds=config.NONCE_RETENTION_SECONDS),
    )
    db.session.add(nonce_record)
    db.session.commit()

    logger.debug("security", "signing", "Request signature verified successfully")
    return True, None
