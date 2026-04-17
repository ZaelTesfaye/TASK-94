"""Unit tests for src/security/lockout.py — login lockout, captcha, and reset."""

from datetime import datetime, timezone, timedelta

import pytest

from src.app import create_app
from src.models.base import db as _db


@pytest.fixture(scope="module")
def app():
    app = create_app(testing=True)
    yield app


@pytest.fixture(scope="function")
def db(app):
    with app.app_context():
        _db.create_all()
        from src.models.models import User
        from src.models.enums import RoleType
        from src.security.passwords import hash_password

        if User.query.first() is None:
            admin = User(
                username="admin",
                password_hash=hash_password("admin"),
                display_name="Platform Administrator",
                role=RoleType.PLATFORM_ADMIN.value,
                is_active=True,
            )
            _db.session.add(admin)
            _db.session.commit()
        yield _db
        _db.session.rollback()
        _db.drop_all()


class TestCheckLockout:
    def test_no_counter_means_not_locked(self, app, db):
        from src.security.lockout import check_lockout

        with app.app_context():
            is_locked, retry_after = check_lockout("unknown-user")
            assert is_locked is False
            assert retry_after == 0

    def test_locked_when_locked_until_in_future(self, app, db):
        from src.security.lockout import check_lockout
        from src.models.models import LoginFailureCounter

        with app.app_context():
            counter = LoginFailureCounter(
                identifier="locked-user",
                failure_count=5,
                locked_until=datetime.now(timezone.utc) + timedelta(minutes=10),
            )
            db.session.add(counter)
            db.session.commit()

            is_locked, retry_after = check_lockout("locked-user")
            assert is_locked is True
            assert retry_after > 0

    def test_not_locked_when_locked_until_expired(self, app, db):
        from src.security.lockout import check_lockout
        from src.models.models import LoginFailureCounter

        with app.app_context():
            counter = LoginFailureCounter(
                identifier="expired-lock-user",
                failure_count=5,
                locked_until=datetime.now(timezone.utc) - timedelta(minutes=1),
            )
            db.session.add(counter)
            db.session.commit()

            is_locked, retry_after = check_lockout("expired-lock-user")
            assert is_locked is False
            assert retry_after == 0


class TestRecordFailure:
    def test_first_failure_creates_counter(self, app, db):
        from src.security.lockout import record_failure
        from src.models.models import LoginFailureCounter

        with app.app_context():
            record_failure("new-user")

            counter = LoginFailureCounter.query.filter_by(identifier="new-user").first()
            assert counter is not None
            assert counter.failure_count == 1
            assert counter.first_failure_at is not None

    def test_increments_on_subsequent_failures(self, app, db):
        from src.security.lockout import record_failure
        from src.models.models import LoginFailureCounter

        with app.app_context():
            record_failure("repeat-user")
            record_failure("repeat-user")
            record_failure("repeat-user")

            counter = LoginFailureCounter.query.filter_by(identifier="repeat-user").first()
            assert counter.failure_count == 3

    def test_lockout_triggered_at_threshold(self, app, db):
        from src.security.lockout import record_failure
        from src.models.models import LoginFailureCounter
        from src.config import config

        with app.app_context():
            identifier = "threshold-user"
            for _ in range(config.LOGIN_MAX_FAILURES):
                record_failure(identifier)

            counter = LoginFailureCounter.query.filter_by(identifier=identifier).first()
            assert counter.failure_count == config.LOGIN_MAX_FAILURES
            assert counter.locked_until is not None
            assert counter.locked_until > datetime.now(timezone.utc)

    def test_no_lockout_at_threshold_minus_one(self, app, db):
        from src.security.lockout import record_failure
        from src.models.models import LoginFailureCounter
        from src.config import config

        with app.app_context():
            identifier = "below-threshold-user"
            for _ in range(config.LOGIN_MAX_FAILURES - 1):
                record_failure(identifier)

            counter = LoginFailureCounter.query.filter_by(identifier=identifier).first()
            assert counter.failure_count == config.LOGIN_MAX_FAILURES - 1
            assert counter.locked_until is None


class TestResetFailures:
    def test_reset_clears_counter(self, app, db):
        from src.security.lockout import record_failure, reset_failures
        from src.models.models import LoginFailureCounter

        with app.app_context():
            record_failure("reset-user")
            record_failure("reset-user")
            record_failure("reset-user")

            reset_failures("reset-user")

            counter = LoginFailureCounter.query.filter_by(identifier="reset-user").first()
            assert counter.failure_count == 0
            assert counter.first_failure_at is None
            assert counter.locked_until is None

    def test_reset_on_nonexistent_user_is_noop(self, app, db):
        from src.security.lockout import reset_failures

        with app.app_context():
            # Should not raise
            reset_failures("nonexistent-user")


class TestNeedsCaptcha:
    def test_no_captcha_needed_below_threshold(self, app, db):
        from src.security.lockout import record_failure, needs_captcha
        from src.config import config

        with app.app_context():
            identifier = "captcha-below"
            for _ in range(config.CAPTCHA_THRESHOLD - 1):
                record_failure(identifier)

            assert needs_captcha(identifier) is False

    def test_captcha_needed_at_threshold(self, app, db):
        from src.security.lockout import record_failure, needs_captcha
        from src.config import config

        with app.app_context():
            identifier = "captcha-at"
            for _ in range(config.CAPTCHA_THRESHOLD):
                record_failure(identifier)

            assert needs_captcha(identifier) is True

    def test_no_captcha_for_unknown_user(self, app, db):
        from src.security.lockout import needs_captcha

        with app.app_context():
            assert needs_captcha("unknown-captcha") is False


class TestCaptchaChallenge:
    def test_create_and_verify_captcha(self, app, db):
        from src.security.lockout import create_captcha_challenge, verify_captcha

        with app.app_context():
            result = create_captcha_challenge("captcha-user", "127.0.0.1")
            assert "challenge_id" in result
            assert "challenge_text" in result
            assert "What is" in result["challenge_text"]

            # Look up expected answer to solve it
            from src.models.models import LoginChallenge
            challenge = LoginChallenge.query.get(result["challenge_id"])
            assert verify_captcha(result["challenge_id"], challenge.expected_answer) is True

    def test_verify_wrong_answer_fails(self, app, db):
        from src.security.lockout import create_captcha_challenge, verify_captcha

        with app.app_context():
            result = create_captcha_challenge("wrong-answer-user", "127.0.0.1")
            assert verify_captcha(result["challenge_id"], "99999") is False

    def test_verify_already_solved_fails(self, app, db):
        from src.security.lockout import create_captcha_challenge, verify_captcha
        from src.models.models import LoginChallenge

        with app.app_context():
            result = create_captcha_challenge("solved-user", "127.0.0.1")
            challenge = LoginChallenge.query.get(result["challenge_id"])
            # Solve it once
            verify_captcha(result["challenge_id"], challenge.expected_answer)
            # Second attempt should fail
            assert verify_captcha(result["challenge_id"], challenge.expected_answer) is False

    def test_verify_expired_captcha_fails(self, app, db):
        from src.security.lockout import create_captcha_challenge, verify_captcha
        from src.models.models import LoginChallenge

        with app.app_context():
            result = create_captcha_challenge("expired-captcha-user", "127.0.0.1")
            # Manually expire it
            challenge = LoginChallenge.query.get(result["challenge_id"])
            challenge.expires_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
            db.session.commit()

            assert verify_captcha(result["challenge_id"], challenge.expected_answer) is False

    def test_verify_nonexistent_challenge_fails(self, app, db):
        from src.security.lockout import verify_captcha

        with app.app_context():
            assert verify_captcha("nonexistent-id", "42") is False
