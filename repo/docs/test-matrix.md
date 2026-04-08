# Test Matrix -- Risk Points and Coverage

Maps identified risk areas to the tests that exercise them and notes any coverage gaps.

## Risk Categories

### Authentication and Session Security

| Risk Point | Test File(s) | Key Test Scenarios | Coverage |
|---|---|---|---|
| Credential stuffing | `tests/api/test_auth.py` | Login lockout after N failures, CAPTCHA trigger at threshold | Covered |
| JWT forgery | `tests/unit/test_tokens.py`, `tests/api/test_auth.py` | Expired token rejected, tampered signature rejected, wrong issuer | Covered |
| Refresh token replay | `tests/api/test_auth.py` | Revoked refresh token rejected, rotation enforced | Covered |
| Session fixation | `tests/api/test_auth.py` | Logout denylists access JTI, logout-all revokes all refresh tokens | Covered |
| Blacklisted device login | `tests/api/test_auth.py`, `tests/api/test_security.py` | Login blocked when device fingerprint is blacklisted | Covered |
| Password hash timing | `tests/unit/test_passwords.py` | Hash and verify round-trip, constant-time comparison | Partial |

### Authorization and RBAC

| Risk Point | Test File(s) | Key Test Scenarios | Coverage |
|---|---|---|---|
| Role escalation | `tests/api/test_permissions.py` | Cannot assign permission to higher-role user | Covered |
| Cross-org data leak | `tests/api/test_permissions.py`, `tests/api/test_invitations.py` | Org admin restricted to own org scope | Covered |
| Invitation role ceiling | `tests/api/test_invitations.py` | Cannot create invitation for role above caller's own | Covered |
| Permission bypass | `tests/api/test_permissions.py` | Non-member cannot assign permissions in foreign org | Covered |

### Booking Integrity

| Risk Point | Test File(s) | Key Test Scenarios | Coverage |
|---|---|---|---|
| Double booking | `tests/api/test_booking.py` | Overlap detection with buffer enforced, concurrent hold rejected | Covered |
| Hold expiry race | `tests/api/test_booking.py` | Expired hold cannot be confirmed | Covered |
| State machine violation | `tests/unit/test_state_machine.py`, `tests/api/test_booking.py` | CANCELLED cannot transition, only valid transitions allowed | Covered |
| Idempotency replay | `tests/api/test_booking.py` | Same idempotency key returns cached response | Covered |
| Quota overflow | `tests/api/test_booking.py` | Slot template quota respected, fallback to resource capacity | Covered |

### Content Governance

| Risk Point | Test File(s) | Key Test Scenarios | Coverage |
|---|---|---|---|
| Duplicate content flood | `tests/api/test_content.py`, `tests/unit/test_normalization.py` | Fingerprint hash collision detected, second post demoted | Covered |
| Rating manipulation | `tests/api/test_content.py` | One rating per user per item (unique constraint), auto-demotion at threshold | Covered |
| Moderation bypass | `tests/api/test_content.py` | Only reviewer/admin can suppress, appeal window enforced | Covered |
| Encrypted notes leak | `tests/unit/test_encryption.py`, `tests/api/test_content.py` | Moderation decision_notes encrypted at rest, non-reviewer sees null | Covered |

### Infrastructure and Transport

| Risk Point | Test File(s) | Key Test Scenarios | Coverage |
|---|---|---|---|
| Request tampering | `tests/api/test_security.py` | Missing/invalid HMAC signature rejected, nonce replay rejected | Covered |
| Rate limit evasion | `tests/api/test_security.py` | Token bucket depleted, 429 returned with retry headers | Covered |
| TLS downgrade | `tests/api/test_security.py` | Non-HTTPS rejected when TLS enabled | Covered |
| Encryption key rotation | `tests/unit/test_encryption.py` | Encrypt/decrypt round-trip with derived key | Partial |

### Analytics and Export

| Risk Point | Test File(s) | Key Test Scenarios | Coverage |
|---|---|---|---|
| Data exfiltration via export | `tests/api/test_analytics.py` | Export org-scoped, only requester can download | Covered |
| Export deduplication | `tests/api/test_analytics.py` | Same parameters within window returns existing export | Covered |
| Difficulty misclassification | `tests/unit/test_difficulty.py` | Threshold boundaries verified for each bucket | Covered |

### Audit Trail

| Risk Point | Test File(s) | Key Test Scenarios | Coverage |
|---|---|---|---|
| Audit record tampering | `tests/api/test_audit.py` | Events are insert-only (no update/delete endpoints) | Covered |
| Alert storm | `tests/api/test_audit.py` | Duplicate alert suppression within time window | Partial |

## Manual Verification Required

- TLS certificate validity and cipher suite configuration (infrastructure-level)
- Production encryption master key strength (operations review)
- Backup restoration from actual backup files (disaster recovery drill)
- Rate limiter behavior under genuine concurrent load (load test)
