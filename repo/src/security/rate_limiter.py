"""Rate limiting with token bucket algorithm - plan section 7 security controls."""

import math
from datetime import datetime, timezone

from src.logging import logger
from src.models.base import db
from src.models.models import RateLimitBucket


def check_rate_limit(
    bucket_key: str,
    max_tokens: int = 60,
    refill_rate: int = 60,
) -> tuple:
    """Check and consume a token from the rate limit bucket.

    Uses a token bucket algorithm with per-minute refill. Each call consumes
    one token if available.

    Args:
        bucket_key: Unique identifier for the rate limit bucket (e.g., "user:123", "ip:10.0.0.1").
        max_tokens: Maximum number of tokens the bucket can hold (burst capacity).
        refill_rate: Number of tokens added per minute.

    Returns:
        Tuple of (allowed: bool, headers: dict) where headers contains:
            X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Reset, Retry-After.
    """
    now = datetime.now(timezone.utc)

    bucket = RateLimitBucket.query.filter_by(bucket_key=bucket_key).first()

    if bucket is None:
        # Create a new bucket with full tokens minus the one being consumed
        bucket = RateLimitBucket(
            bucket_key=bucket_key,
            tokens=max_tokens - 1,
            last_refill_at=now,
        )
        db.session.add(bucket)
        db.session.commit()

        headers = _build_headers(max_tokens, max_tokens - 1, now)
        logger.debug("security", "rate_limiter", f"New bucket created: {bucket_key}")
        return True, headers

    # Calculate tokens to refill based on elapsed time
    last_refill = bucket.last_refill_at
    if last_refill.tzinfo is None:
        last_refill = last_refill.replace(tzinfo=timezone.utc)
    elapsed_seconds = (now - last_refill).total_seconds()
    elapsed_minutes = elapsed_seconds / 60.0
    tokens_to_add = int(elapsed_minutes * refill_rate)

    if tokens_to_add > 0:
        bucket.tokens = min(max_tokens, bucket.tokens + tokens_to_add)
        bucket.last_refill_at = now

    if bucket.tokens > 0:
        bucket.tokens -= 1
        db.session.commit()

        headers = _build_headers(max_tokens, bucket.tokens, now)
        logger.debug("security", "rate_limiter", f"Token consumed: {bucket_key}, remaining={bucket.tokens}")
        return True, headers
    else:
        db.session.commit()

        # Calculate when the next token will be available
        seconds_per_token = 60.0 / refill_rate
        retry_after = math.ceil(seconds_per_token)
        reset_time = now.timestamp() + retry_after

        headers = {
            "X-RateLimit-Limit": str(max_tokens),
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": str(int(reset_time)),
            "Retry-After": str(retry_after),
        }
        logger.warning("security", "rate_limiter", f"Rate limit exceeded: {bucket_key}")
        return False, headers


def _build_headers(max_tokens: int, remaining: int, now: datetime) -> dict:
    """Build standard rate limit response headers."""
    reset_time = now.timestamp() + 60  # Reset window is 1 minute
    return {
        "X-RateLimit-Limit": str(max_tokens),
        "X-RateLimit-Remaining": str(remaining),
        "X-RateLimit-Reset": str(int(reset_time)),
        "Retry-After": "0",
    }
