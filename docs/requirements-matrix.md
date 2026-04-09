# Requirements Traceability Matrix

Maps each functional requirement area to its implementation source, test coverage, and current status.

## Legend

- **Done**: Implementation complete and tests passing
- **Partial**: Implementation exists but tests incomplete or edge cases remain
- **Pending**: Not yet implemented

## Core Domains

| Requirement Area | Implementation File(s) | Test File(s) | Status |
|---|---|---|---|
| Guest registration | `src/api/auth.py` | `tests/api/test_auth.py` | Done |
| Login with credentials | `src/api/auth.py` | `tests/api/test_auth.py` | Done |
| JWT access/refresh tokens | `src/security/tokens.py`, `src/api/auth.py` | `tests/unit/test_tokens.py`, `tests/api/test_auth.py` | Done |
| Token refresh with rotation | `src/api/auth.py` | `tests/api/test_auth.py` | Done |
| Logout / logout-all | `src/api/auth.py` | `tests/api/test_auth.py` | Done |
| Device bind / unbind | `src/api/auth.py` | `tests/api/test_auth.py` | Done |
| Device fingerprint blacklisting | `src/api/auth.py`, `src/security/encryption.py` | `tests/api/test_auth.py`, `tests/api/test_security.py` | Done |
| CAPTCHA after failed logins | `src/security/lockout.py`, `src/api/auth.py` | `tests/api/test_auth.py` | Done |
| Login lockout | `src/security/lockout.py` | `tests/api/test_auth.py` | Done |
| RBAC role hierarchy | `src/models/enums.py`, `src/security/auth_middleware.py` | `tests/unit/test_enums.py`, `tests/api/test_permissions.py` | Done |
| Permission create / assign / revoke | `src/api/permissions.py` | `tests/api/test_permissions.py` | Done |
| Membership list / context switch | `src/api/permissions.py` | `tests/api/test_permissions.py` | Done |
| Invitation create / list / redeem / revoke | `src/api/invitations.py` | `tests/api/test_invitations.py` | Done |
| Resource CRUD | `src/api/booking.py` | `tests/api/test_booking.py` | Done |
| Slot template management | `src/api/booking.py` | `tests/api/test_booking.py` | Done |
| Hold / confirm / cancel / reschedule | `src/api/booking.py` | `tests/api/test_booking.py` | Done |
| Booking overlap detection with buffer | `src/api/booking.py` | `tests/api/test_booking.py` | Done |
| Idempotency for booking mutations | `src/api/booking.py` | `tests/api/test_booking.py` | Done |
| Content create / list / get | `src/api/content.py` | `tests/api/test_content.py` | Done |
| Duplicate content detection (fingerprint) | `src/api/content.py` | `tests/api/test_content.py`, `tests/unit/test_normalization.py` | Done |
| Rating & auto-demotion | `src/api/content.py` | `tests/api/test_content.py` | Done |
| Comments / favorites / downloads | `src/api/content.py` | `tests/api/test_content.py` | Done |
| Moderation (report / suppress / reinstate) | `src/api/content.py` | `tests/api/test_content.py` | Done |
| Appeal flow | `src/api/content.py` | `tests/api/test_content.py` | Done |
| Learning event ingest | `src/api/analytics.py` | `tests/api/test_analytics.py` | Done |
| Completion / behavior analytics | `src/api/analytics.py` | `tests/api/test_analytics.py` | Done |
| Difficulty classification | `src/api/analytics.py`, `src/models/enums.py` | `tests/unit/test_difficulty.py`, `tests/api/test_analytics.py` | Done |
| CSV export with deduplication | `src/api/analytics.py` | `tests/api/test_analytics.py` | Done |
| Audit event logging (immutable) | `src/api/audit.py` | `tests/api/test_audit.py` | Done |
| Alerts (create / ack / resolve) | `src/api/audit.py` | `tests/api/test_audit.py` | Done |
| System status / debug endpoints | `src/api/admin.py` | `tests/api/test_admin.py` | Done |
| Health check | `src/api/health.py` | `tests/api/test_admin.py` | Done |

## Cross-Cutting Concerns

| Requirement Area | Implementation File(s) | Test File(s) | Status |
|---|---|---|---|
| Request signing (HMAC-SHA256) | `src/security/signing.py`, `src/app.py` | `tests/api/test_security.py` | Done |
| Rate limiting (token bucket) | `src/security/rate_limiter.py`, `src/app.py` | `tests/api/test_security.py` | Done |
| TLS enforcement | `src/app.py` | `tests/api/test_security.py` | Done |
| AES-256-GCM encryption at rest | `src/security/encryption.py` | `tests/unit/test_encryption.py` | Done |
| Password hashing | `src/security/passwords.py` | `tests/unit/test_passwords.py` | Done |
| Input validation | `src/utils/validators.py` | `tests/unit/test_validators.py` | Done |
| Pagination | `src/utils/pagination.py` | (covered by API tests) | Done |
| Centralized config | `src/config/__init__.py` | (covered by integration tests) | Done |
| Structured logging | `src/logging.py` | (covered by integration tests) | Done |
| State machine transitions | `src/models/enums.py` | `tests/unit/test_state_machine.py` | Done |
| Scheduled backup | `src/scheduler.py` (optional) | -- | Partial |
