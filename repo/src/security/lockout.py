"""Login lockout and captcha challenge - plan section 7 security controls."""

import random
import uuid
from datetime import datetime, timedelta, timezone

from src.config import config
from src.logging import logger
from src.models.base import db
from src.models.models import LoginFailureCounter, LoginChallenge


def check_lockout(identifier: str) -> tuple:
    """Check whether an identifier (username or IP) is currently locked out.

    Args:
        identifier: The login identifier to check (username, IP, etc.).

    Returns:
        Tuple of (is_locked: bool, retry_after_seconds: int).
    """
    counter = LoginFailureCounter.query.filter_by(identifier=identifier).first()
    if counter is None:
        return False, 0

    locked_until = counter.locked_until
    if locked_until and locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=timezone.utc)
    if locked_until and locked_until > datetime.now(timezone.utc):
        remaining = (locked_until - datetime.now(timezone.utc)).total_seconds()
        logger.warning("security", "lockout", f"Account locked: {identifier}, retry_after={int(remaining)}s")
        return True, int(remaining)

    return False, 0


def record_failure(identifier: str) -> None:
    """Record a failed login attempt and apply lockout if threshold exceeded.

    Args:
        identifier: The login identifier that failed.
    """
    now = datetime.now(timezone.utc)
    counter = LoginFailureCounter.query.filter_by(identifier=identifier).first()

    if counter is None:
        counter = LoginFailureCounter(
            identifier=identifier,
            failure_count=1,
            first_failure_at=now,
        )
        db.session.add(counter)
    else:
        counter.failure_count += 1
        if counter.first_failure_at is None:
            counter.first_failure_at = now

    # Apply lockout if max failures exceeded
    if counter.failure_count >= config.LOGIN_MAX_FAILURES:
        counter.locked_until = now + timedelta(minutes=config.LOGIN_LOCKOUT_MINUTES)
        logger.warning(
            "security", "lockout",
            f"Account locked after {counter.failure_count} failures: {identifier}"
        )

    db.session.commit()
    logger.info("security", "lockout", f"Login failure recorded: {identifier}, count={counter.failure_count}")


def reset_failures(identifier: str) -> None:
    """Reset the failure counter on successful login.

    Args:
        identifier: The login identifier to reset.
    """
    counter = LoginFailureCounter.query.filter_by(identifier=identifier).first()
    if counter:
        counter.failure_count = 0
        counter.first_failure_at = None
        counter.locked_until = None
        db.session.commit()
        logger.info("security", "lockout", f"Failure counter reset: {identifier}")


def needs_captcha(identifier: str) -> bool:
    """Check if captcha verification is required for the given identifier.

    Args:
        identifier: The login identifier to check.

    Returns:
        True if the failure count meets or exceeds the captcha threshold.
    """
    counter = LoginFailureCounter.query.filter_by(identifier=identifier).first()
    if counter is None:
        return False
    return counter.failure_count >= config.CAPTCHA_THRESHOLD


def create_captcha_challenge(identifier: str, ip: str) -> dict:
    """Create a simple math captcha challenge.

    Args:
        identifier: The login identifier requesting the captcha.
        ip: The client IP address.

    Returns:
        Dict with challenge_id and challenge_text (e.g., "What is 7 + 3?").
    """
    a = random.randint(1, 20)
    b = random.randint(1, 20)
    expected_answer = str(a + b)
    challenge_text = f"What is {a} + {b}?"

    challenge = LoginChallenge(
        ip_address=ip,
        challenge_type="captcha",
        challenge_data=challenge_text,
        expected_answer=expected_answer,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )

    # Link to user if identifier matches a user lookup context
    # (caller can set user_id separately if needed)
    db.session.add(challenge)
    db.session.commit()

    logger.info("security", "lockout", f"Captcha challenge created for {identifier} from {ip}")
    return {
        "challenge_id": challenge.id,
        "challenge_text": challenge_text,
    }


def verify_captcha(challenge_id: str, answer: str) -> bool:
    """Verify a captcha challenge answer.

    Args:
        challenge_id: The ID of the challenge to verify.
        answer: The user's answer string.

    Returns:
        True if the answer is correct and the challenge is still valid.
    """
    challenge = LoginChallenge.query.filter_by(id=challenge_id).first()
    if challenge is None:
        logger.warning("security", "lockout", f"Captcha challenge not found: {challenge_id}")
        return False

    if challenge.is_solved:
        logger.warning("security", "lockout", f"Captcha already solved: {challenge_id}")
        return False

    ch_expires = challenge.expires_at
    if ch_expires.tzinfo is None:
        ch_expires = ch_expires.replace(tzinfo=timezone.utc)
    if ch_expires < datetime.now(timezone.utc):
        logger.warning("security", "lockout", f"Captcha expired: {challenge_id}")
        return False

    if str(answer).strip() == challenge.expected_answer:
        challenge.is_solved = True
        db.session.commit()
        logger.info("security", "lockout", f"Captcha verified: {challenge_id}")
        return True

    logger.warning("security", "lockout", f"Captcha answer incorrect: {challenge_id}")
    return False
