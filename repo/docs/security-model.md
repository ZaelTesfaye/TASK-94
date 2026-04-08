# Security Model

Describes all security controls, where they are enforced, and boundaries that require manual verification.

## 1. Authentication

### JWT Token Lifecycle

- **Algorithm**: HS256 (configurable via `JWT_ALGORITHM`)
- **Access token TTL**: 30 minutes (configurable via `JWT_ACCESS_TOKEN_EXPIRES_MINUTES`)
- **Refresh token TTL**: 14 days (configurable via `JWT_REFRESH_TOKEN_EXPIRES_DAYS`)
- **Issuer claim**: `learning-booking-api` (configurable via `JWT_ISSUER`)
- **Enforcement**: `src/security/auth_middleware.py` (`require_auth` decorator)
- **Token rotation**: Refresh endpoint revokes the old refresh token and issues a new pair
- **Denylist**: Logout places access token JTI on `access_token_denylist` table; middleware checks before granting access
- **Refresh token storage**: HMAC-SHA256 keyed hash stored encrypted at rest (AES-256-GCM via `EncryptedText` in `token_hash` column), with a deterministic `token_lookup_hash` for indexed queries. Raw token never persisted.

### Login Lockout

- **Implementation**: `src/security/lockout.py`
- **Threshold**: 5 failures triggers lockout (configurable via `LOGIN_MAX_FAILURES`)
- **Duration**: 15 minutes (configurable via `LOGIN_LOCKOUT_MINUTES`)
- **Tracking**: `login_failure_counters` table keyed by username
- **Reset**: Counter resets on successful login

### CAPTCHA Challenge

- **Trigger**: After 3 failed attempts (configurable via `CAPTCHA_THRESHOLD`)
- **Implementation**: `src/security/lockout.py` generates a math-based challenge stored in `login_challenges` table
- **Enforcement**: `src/api/auth.py` login endpoint checks `needs_captcha()` before credential verification
- **Expiry**: Challenge records expire and are single-use (`is_solved` flag)

### Device Fingerprint Blacklisting

- **Storage**: `devices` table with `fingerprint_hash` (AES-256-GCM encrypted) and `fingerprint_lookup_hash` (HMAC-SHA256 deterministic)
- **Blacklist check**: Login endpoint queries `fingerprint_lookup_hash` for `BLACKLISTED` status
- **Retry window**: 168 hours / 7 days (configurable via `DEVICE_BLACKLIST_RETRY_AFTER_HOURS`)
- **Risk score threshold**: 0.9 (configurable via `DEVICE_RISK_BLACKLIST_THRESHOLD`)
- **Risk accumulation**: Each failed login increments the device risk score by `DEVICE_RISK_INCREMENT_PER_FAILURE` (default 0.15). When the accumulated score reaches or exceeds the threshold, the device is automatically blacklisted with a cooldown period and a `DEVICE_BLACKLISTED` audit event is emitted.

## 2. Authorization (RBAC)

### Role Hierarchy

| Level | Role | Scope |
|---|---|---|
| 3 | `platform_admin` | Full system access |
| 2 | `org_admin` | Organization-scoped management |
| 1 | `member` | Standard authenticated user |
| 0 | `guest` | Minimal access, self-registered |

- **Enforcement**: `require_role()` decorator in `src/security/auth_middleware.py`
- **Hierarchy rule**: A caller can only manage users/permissions at or below their own role level
- **Org boundary**: Non-platform-admins are scoped to their organization via `Membership` table

### Permission System

- **Model**: `permissions` defines permission codes; `user_permissions` assigns them per user per org
- **Enforcement**: `require_permission()` decorator checks JWT claims and verifies against the database with org-scope validation. Platform admins bypass permission checks (implicit full access).
- **Claim embedding**: Permission codes are embedded in the access token at login/refresh
- **Object-level authorization**: Moderation decision and appeal-decision endpoints enforce four layers: (1) `require_org_context` ensures an org context exists, (2) `require_role("org_admin")` enforces the Org Admin+ contract, (3) `require_permission("moderation:review")` validates the DB-level org-scoped grant, (4) `verify_org_scope(content_item.organization_id)` confirms the content's org matches the caller's org. Platform admins bypass all four.

## 3. Transport Security

### TLS Enforcement

- **Toggle**: `ENABLE_TLS` config flag (default: `true`)
- **Enforcement**: `before_request` hook in `src/app.py` checks `X-Forwarded-Proto` or `request.scheme`
- **Response**: 403 `TLS_REQUIRED` if non-HTTPS detected
- **Certificate paths**: `/app/certs/cert.pem`, `/app/certs/key.pem`

### Request Signing (HMAC-SHA256)

- **Implementation**: `src/security/signing.py`
- **Enforcement**: `before_request` hook in `src/app.py`
- **Exempt paths**: `/health`
- **Clock skew tolerance**: +/- 300 seconds (configurable via `REQUEST_SIGNING_SKEW_SECONDS`)
- **Nonce replay protection**: `nonce_store` table, retention 600 seconds (configurable via `NONCE_RETENTION_SECONDS`)

### Security Response Headers

Set in `after_request` hook in `src/app.py`:
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Cache-Control: no-store` on `/auth` and `/admin` routes

## 4. Rate Limiting

- **Algorithm**: Token bucket
- **Implementation**: `src/security/rate_limiter.py`, state in `rate_limit_buckets` table
- **Enforcement**: `before_request` hook in `src/app.py`
- **Default rate**: 60 requests/minute (configurable via `RATE_LIMIT_DEFAULT_PER_MINUTE`)
- **Burst**: 20 tokens (configurable via `RATE_LIMIT_BURST`)
- **Bucket key**: `ip:<remote_addr>` for unauthenticated requests
- **Exempt paths**: `/health`
- **Response**: 429 with `Retry-After` and `X-RateLimit-*` headers

## 5. Encryption at Rest

- **Algorithm**: AES-256-GCM via `cryptography` library
- **Key derivation**: HKDF-SHA256 from `ENCRYPTION_MASTER_KEY` with context-specific info strings
- **Implementation**: `src/security/encryption.py`
- **SQLAlchemy integration**: `EncryptedText` custom type in `src/models/models.py`
- **Encrypted fields**: `moderation_cases.decision_notes`, `moderation_cases.appeal_notes`, `moderation_cases.appeal_decision_notes`
- **Device fingerprint**: Encrypted via AES-256-GCM for storage, HMAC-SHA256 for deterministic lookup

## 6. Audit Trail

- **Table**: `audit_events` (insert-only, no update/delete endpoints exposed)
- **Coverage**: All auth events, permission changes, booking state transitions, content actions, moderation decisions, export/backup operations
- **Fields**: `event_type`, `actor_id`, `actor_ip`, `target_type`, `target_id`, `organization_id`, `before_state`, `after_state`
- **Alert integration**: `alerts` table with severity levels, auto-generated on login failure spikes and booking conflict spikes

## 7. Manual Verification Boundaries

These controls depend on deployment configuration and cannot be fully verified by automated tests:

| Control | What to Verify |
|---|---|
| TLS certificate | Valid cert chain, strong cipher suite, no expired certs |
| Encryption master key | Production key is >= 32 bytes, stored in secret manager, not in source control |
| Signing secret | Production secret differs from defaults, rotated periodically |
| JWT secret key | Production key differs from default, sufficient entropy |
| Database file permissions | SQLite file not world-readable; or use PostgreSQL with auth in production |
| Backup encryption | Backup files at `/app/backups` are access-controlled and optionally encrypted |
| Container isolation | Docker volumes for data, exports, backups are not exposed to host unnecessarily |
| Rate limiter tuning | Thresholds appropriate for production traffic patterns |

## 8. Booking Overlap — SQLite Concurrency Strategy

SQLite cannot enforce general interval exclusion constraints at the DB level (that requires
range exclusion operators only available in PostgreSQL). The booking engine uses a three-layer
defence to prevent double-booking / overselling:

1. **`BEGIN IMMEDIATE`** — issued before the overlap check in `src/api/booking.py` (`create_hold`).
   This acquires an exclusive write lock on the database so the read-check-then-insert sequence
   is atomic with respect to other writers. Any concurrent writer blocks until the transaction
   commits or rolls back.

2. **Application-level interval intersection query** — `_check_overlap()` uses the standard
   interval overlap predicate (`existing.start_time < new.end_time AND existing.end_time > new.start_time`,
   with configurable buffer) to detect conflicts among `HELD` and `CONFIRMED` reservations.
   This catches partial overlaps (e.g. 10:00–11:00 vs 10:30–11:30), not just exact duplicates.

3. **Partial unique index + `IntegrityError` catch** — a unique index on
   `(resource_id, start_time, end_time) WHERE status IN ('HELD','CONFIRMED')` acts as a
   safety net for the exact-duplicate race. The `IntegrityError` handler in the hold endpoint
   rolls back and returns `409 SLOT_UNAVAILABLE`.

**Migration to PostgreSQL**: When moving to PostgreSQL, replace layers 1 and 3 with an
`EXCLUDE USING gist` constraint on `(resource_id WITH =, tstzrange(start_time, end_time) WITH &&)`
and remove the `BEGIN IMMEDIATE` call (PostgreSQL uses MVCC, not file-level locking).
The application-level check (layer 2) can remain as a user-friendly pre-check.
