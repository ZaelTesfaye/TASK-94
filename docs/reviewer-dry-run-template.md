# Reviewer Dry-Run Template

Structured template for section-by-section review of the Learning & Resource Booking Governance API. Fill in each decision field during the review pass.

---

## Review Metadata

| Field | Value |
|---|---|
| Reviewer | ________ |
| Date | ________ |
| Commit / Branch | ________ |
| Review Type | [ ] Initial  [ ] Re-review  [ ] Focused |

---

## 1. Authentication (src/api/auth.py, src/security/)

### 1.1 Registration
- [ ] Guest registration creates user with `guest` role
- [ ] Password is hashed before storage (never stored as plaintext)
- [ ] Duplicate username returns 409
- **Decision**: [ ] Approve  [ ] Request Changes  [ ] Defer
- **Notes**: ________

### 1.2 Login Flow
- [ ] Lockout enforced after configured failure threshold
- [ ] CAPTCHA challenge generated after configured failure count
- [ ] Blacklisted device fingerprint blocks login
- [ ] Successful login resets failure counter
- [ ] Access and refresh tokens issued on success
- [ ] Failed login creates audit event
- [ ] Login failure spike triggers alert creation
- **Decision**: [ ] Approve  [ ] Request Changes  [ ] Defer
- **Notes**: ________

### 1.3 Token Management
- [ ] Refresh rotates tokens (old revoked, new issued)
- [ ] Logout denylists access token JTI
- [ ] Logout-all revokes all refresh tokens for user
- [ ] Expired/revoked tokens rejected by middleware
- **Decision**: [ ] Approve  [ ] Request Changes  [ ] Defer
- **Notes**: ________

### 1.4 Device Management
- [ ] Bind stores encrypted fingerprint + deterministic lookup hash
- [ ] Unbind removes device record
- [ ] Risk score and blacklist status tracked
- **Decision**: [ ] Approve  [ ] Request Changes  [ ] Defer
- **Notes**: ________

---

## 2. Authorization (src/api/permissions.py, src/security/auth_middleware.py)

### 2.1 RBAC Enforcement
- [ ] Role hierarchy enforced (guest < member < org_admin < platform_admin)
- [ ] `require_role` decorator blocks insufficient roles
- [ ] `require_permission` decorator checks JWT permission claims
- **Decision**: [ ] Approve  [ ] Request Changes  [ ] Defer
- **Notes**: ________

### 2.2 Permission Management
- [ ] Only platform admin can create permission definitions
- [ ] Assign/revoke requires org_admin+ and org membership
- [ ] Cannot assign permissions to users with higher role
- [ ] Cross-org boundary enforced for non-platform-admins
- **Decision**: [ ] Approve  [ ] Request Changes  [ ] Defer
- **Notes**: ________

### 2.3 Memberships
- [ ] List returns only caller's memberships (unless platform admin)
- [ ] Context switch validates active membership exists
- **Decision**: [ ] Approve  [ ] Request Changes  [ ] Defer
- **Notes**: ________

---

## 3. Invitations (src/api/invitations.py)

- [ ] Create restricted to org_admin+ with org membership check
- [ ] Target role cannot exceed caller's role
- [ ] Redeem creates/updates membership, marks invitation REDEEMED
- [ ] Expired invitations auto-transition to EXPIRED status
- [ ] Revoke only works on PENDING invitations
- [ ] All actions produce audit events
- **Decision**: [ ] Approve  [ ] Request Changes  [ ] Defer
- **Notes**: ________

---

## 4. Booking (src/api/booking.py)

### 4.1 Resource and Slot Management
- [ ] Resource CRUD restricted to org_admin+
- [ ] Slot templates define recurring availability windows
- **Decision**: [ ] Approve  [ ] Request Changes  [ ] Defer
- **Notes**: ________

### 4.2 Reservation Lifecycle
- [ ] Hold checks overlap with buffer period
- [ ] Hold respects slot quota (template or resource capacity fallback)
- [ ] Hold expiry time set from config
- [ ] Confirm validates hold has not expired
- [ ] Cancel and reschedule follow state machine transitions
- [ ] Idempotency key prevents duplicate operations
- [ ] Version field supports optimistic concurrency
- [ ] Booking conflict spike triggers alert
- **Decision**: [ ] Approve  [ ] Request Changes  [ ] Defer
- **Notes**: ________

---

## 5. Content Governance (src/api/content.py)

### 5.1 Content Lifecycle
- [ ] Create computes fingerprint hash for duplicate detection
- [ ] Duplicate fingerprint demotes the newer item
- [ ] Rating auto-demotion at threshold (min count + avg below threshold)
- **Decision**: [ ] Approve  [ ] Request Changes  [ ] Defer
- **Notes**: ________

### 5.2 Moderation
- [ ] Report creates moderation case
- [ ] Review (suppress/reinstate) restricted to reviewer/admin
- [ ] Appeal window enforced (days configurable)
- [ ] Appeal notes minimum length validated
- [ ] Decision notes encrypted at rest (AES-256-GCM)
- [ ] Non-reviewer users cannot see encrypted notes
- **Decision**: [ ] Approve  [ ] Request Changes  [ ] Defer
- **Notes**: ________

---

## 6. Analytics (src/api/analytics.py)

- [ ] Learning event ingest validates event type enum
- [ ] Completion and behavior endpoints org-scoped
- [ ] Difficulty classification matches threshold boundaries
- [ ] CSV export with deduplication (parameters hash + time window)
- [ ] Download restricted to export requester / org admin
- **Decision**: [ ] Approve  [ ] Request Changes  [ ] Defer
- **Notes**: ________

---

## 7. Audit and Alerts (src/api/audit.py)

- [ ] Audit events are read-only (no update/delete endpoints)
- [ ] Audit query supports filtering by event_type, actor, date range
- [ ] Alerts follow OPEN -> ACKNOWLEDGED -> RESOLVED lifecycle
- [ ] Org-scoping enforced for non-platform-admins
- **Decision**: [ ] Approve  [ ] Request Changes  [ ] Defer
- **Notes**: ________

---

## 8. Security Controls (src/security/, src/app.py)

### 8.1 Transport
- [ ] TLS enforcement rejects non-HTTPS when enabled
- [ ] Request signing validates HMAC-SHA256 with nonce replay protection
- [ ] Security headers set on all responses (X-Content-Type-Options, X-Frame-Options, Referrer-Policy)
- [ ] Cache-Control: no-store on /auth and /admin routes
- **Decision**: [ ] Approve  [ ] Request Changes  [ ] Defer
- **Notes**: ________

### 8.2 Rate Limiting
- [ ] Token bucket algorithm implemented
- [ ] 429 response includes retry headers
- [ ] Health endpoint exempt from rate limiting
- **Decision**: [ ] Approve  [ ] Request Changes  [ ] Defer
- **Notes**: ________

### 8.3 Encryption at Rest
- [ ] AES-256-GCM with HKDF key derivation
- [ ] EncryptedText type auto-encrypts/decrypts in SQLAlchemy
- [ ] Device fingerprint uses separate HMAC-SHA256 for lookups
- **Decision**: [ ] Approve  [ ] Request Changes  [ ] Defer
- **Notes**: ________

---

## 9. Configuration and Operations (src/config/, docker-compose.yml)

- [ ] All secrets have non-production defaults with clear "change-me" markers
- [ ] Config loaded exclusively from environment variables via `_Config` class
- [ ] Debug endpoints gated behind `ENABLE_DEBUG_ENDPOINTS` flag
- [ ] Redacted config endpoint masks sensitive values
- [ ] Docker volumes for data, exports, backups correctly mounted
- **Decision**: [ ] Approve  [ ] Request Changes  [ ] Defer
- **Notes**: ________

---

## 10. Test Coverage (tests/)

- [ ] API integration tests exist for all 8 modules
- [ ] Unit tests cover tokens, passwords, encryption, validators, enums, state machine, normalization, difficulty
- [ ] Security tests cover TLS, signing, rate limiting
- [ ] No test files reference hardcoded production secrets
- **Decision**: [ ] Approve  [ ] Request Changes  [ ] Defer
- **Notes**: ________

---

## Overall Verdict

| Aspect | Status |
|---|---|
| Functional correctness | [ ] Pass  [ ] Fail  [ ] Conditional |
| Security posture | [ ] Pass  [ ] Fail  [ ] Conditional |
| Test coverage adequacy | [ ] Pass  [ ] Fail  [ ] Conditional |
| Operational readiness | [ ] Pass  [ ] Fail  [ ] Conditional |
| **Overall** | [ ] Approve  [ ] Request Changes  [ ] Reject |

**Summary**: ________

**Blocking issues**: ________

**Follow-up items**: ________
