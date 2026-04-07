# questions.md

## 1. Platform Admin Bootstrap

**Question:** The prompt does not specify how the first platform_admin account is created when the system starts with an empty database.
**Assumption:** There must be a deterministic way to create the initial admin without an existing admin.
**Solution:** On first startup with no users, automatically seed a default platform_admin account with credentials from environment variables (e.g., `ADMIN_USERNAME`, `ADMIN_PASSWORD`) or require a one-time bootstrap CLI command.

---

## 2. Guest Registration vs Invitation-Only Members

**Question:** The prompt mentions guests, members, and invitation codes but does not clarify if guests can self-register or if all accounts require invitations.
**Assumption:** Guests can self-register openly, but member/org_admin roles require an invitation code redemption.
**Solution:** Allow open registration for guest role only; member and higher roles are assigned exclusively through invitation code redemption or platform_admin elevation.

---

## 3. Invitation Code Generator and Issuer Roles

**Question:** The prompt specifies invite codes expire after 72 hours and are redeemable once, but does not define who can create them or what role the redeemer receives.
**Assumption:** Only org_admin and platform_admin can issue invites; the target role must be specified at creation time.
**Solution:** Invite creation requires org_admin or platform_admin; payload includes target_role (member or org_admin), target_organization_id, expiry timestamp; redemption assigns exactly that role within that organization scope.

---

## 4. Multi-Organization Membership

**Question:** The prompt does not specify whether a single user can belong to multiple organizations simultaneously.
**Assumption:** Users can hold memberships in multiple organizations, each with independent roles and data-scope.
**Solution:** Store one Membership row per (user_id, organization_id) pair; enforce data-scope checks using the membership's organization context on each request.

---

## 5. Role Hierarchy Inheritance

**Question:** The prompt lists roles (guest, member, org_admin, platform_admin) but does not define whether higher roles inherit lower role permissions.
**Assumption:** Role hierarchy is strictly cumulative (platform_admin inherits all lower permissions).
**Solution:** Implement additive inheritance: member has all guest permissions plus member-specific; org_admin has all member permissions scoped to their org; platform_admin has unrestricted access.

---

## 6. Permission Action Codes

**Question:** The prompt mentions configurable permissions at action and data-scope level but does not list which action codes exist.
**Assumption:** Without explicit action codes, authorization checks will be inconsistent.
**Solution:** Define canonical action codes for each domain: `booking:create`, `booking:confirm`, `booking:cancel`, `booking:reschedule`, `content:create`, `content:rate`, `content:report`, `moderation:review`, `moderation:appeal`, `analytics:view`, `export:create`, `admin:manage_users`, `admin:manage_permissions`, etc.

---

## 7. Device Fingerprint Generation Method

**Question:** The prompt references "locally generated device fingerprint" for optional device binding but does not specify the generation algorithm.
**Assumption:** The client is responsible for generating the fingerprint; the server only stores and validates it.
**Solution:** Client generates fingerprint by hashing a combination of User-Agent, Accept-Language, screen resolution, timezone offset, and installed fonts (or similar stable attributes) using SHA-256. Server stores fingerprint on first login and optionally binds subsequent sessions.

---

## 8. Device Binding Opt-In Mechanism

**Question:** The prompt says device binding is "optional" but does not specify how a user opts in or out.
**Assumption:** Device binding must be an explicit user action, not automatic.
**Solution:** Provide a `POST /auth/device/bind` endpoint that the authenticated user calls with their current fingerprint to enable binding; include a `POST /auth/device/unbind` to remove binding.

---

## 9. High-Risk Fingerprint Definition

**Question:** The prompt mentions "repeated high-risk fingerprints can be blacklisted" but does not define what makes a fingerprint high-risk.
**Assumption:** Risk scoring must use measurable criteria.
**Solution:** Increment risk_score on: failed login attempts (e.g., +10 per failure), password reset requests (+5), anomalous geolocation jumps (+20). Blacklist threshold is configurable (default: risk_score >= 100); blacklisted_until set to now + 7 days.

---

## 10. Blacklisted Device Login Behavior

**Question:** The prompt does not specify what happens when a blacklisted device attempts to log in.
**Assumption:** The system must reject login attempts from blacklisted devices with a clear error.
**Solution:** Return HTTP 403 with error code `DEVICE_BLACKLISTED` and include `retry_after` timestamp. Successful logins from non-blacklisted devices do not automatically clear other blacklisted fingerprints.

---

## 11. Access Token Payload Structure

**Question:** The prompt defines 30-minute access tokens but does not specify the payload structure.
**Assumption:** Token must contain sufficient claims for stateless authorization checks.
**Solution:** JWT payload includes: `sub` (user_id), `iat`, `exp`, `roles` (list of role codes), `org_scopes` (list of {org_id, role, data_scope}), `device_fingerprint` (if bound), `jti` (unique token id for revocation checks).

---

## 12. Refresh Token Storage and Rotation

**Question:** The prompt specifies 14-day refresh tokens but does not define whether they are rotated on use or static.
**Assumption:** Security best practice requires refresh token rotation.
**Solution:** On each token refresh, invalidate the old refresh token and issue a new one with fresh 14-day expiry. Store refresh tokens in database with (token_hash, user_id, device_fingerprint, issued_at, expires_at, revoked_at).

---

## 13. Logout Token Invalidation

**Question:** The prompt does not specify whether logout invalidates only the current token or all user sessions.
**Assumption:** Logout should invalidate only the current session by default.
**Solution:** `POST /auth/logout` revokes the current access token's jti and its associated refresh token. Provide separate `POST /auth/logout-all` endpoint for platform_admin or self-service to revoke all sessions.

---

## 14. Request Signing Algorithm

**Question:** The prompt requires request signing with nonce+timestamp for anti-replay but does not specify the exact algorithm.
**Assumption:** Without a defined algorithm, implementations will be inconsistent.
**Solution:** Signature = HMAC-SHA256(secret_key, `{method}:{path}:{timestamp}:{nonce}:{body_hash}`) where body_hash is SHA-256 of request body (empty string hash if no body). Headers required: `X-Timestamp`, `X-Nonce`, `X-Signature`.

---

## 15. Nonce Storage and Replay Window

**Question:** The prompt mentions nonce for anti-replay but does not specify how long nonces are stored to detect replay.
**Assumption:** Nonces must be stored at least as long as the timestamp skew window.
**Solution:** Store nonces for 10 minutes (5-min skew \* 2 for safety margin). Reject requests with reused nonce within this window. Purge expired nonces via scheduled cleanup.

---

## 16. Which Endpoints Require Signed Requests

**Question:** The prompt does not specify whether all endpoints require request signing or only sensitive ones.
**Assumption:** Signing all requests is excessive; sensitive mutations need signing.
**Solution:** Require signed requests for: all booking mutations (create, confirm, cancel, reschedule), auth endpoints (login, logout, refresh), permission changes, and moderation decisions. Read-only endpoints (GET) do not require signing.

---

## 17. Rate Limiting Response Headers

**Question:** The prompt specifies 60 requests/minute with burst 20 but does not define response behavior when limits are exceeded.
**Assumption:** Clients need retry information to implement backoff.
**Solution:** Return HTTP 429 with headers: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` (Unix timestamp), `Retry-After` (seconds until reset).

---

## 18. Rate Limit Scope Separation

**Question:** The prompt mentions per-identity and per-IP rate limiting but does not clarify if they are independent or combined.
**Assumption:** Both limits apply independently.
**Solution:** Track separate buckets for IP-based (unauthenticated) and identity-based (authenticated) limits. A request can fail either limit independently. Authenticated requests count against both IP and identity buckets.

---

## 19. Local CAPTCHA Challenge Implementation

**Question:** The prompt requires a "local CAPTCHA-style challenge" after 5 failed logins but does not define what this entails without third-party services.
**Assumption:** A local challenge must be implementable without external dependencies.
**Solution:** Generate a simple math challenge (e.g., "What is 7 + 3?") or text-based question stored server-side with a challenge_id. Client must submit correct answer before login attempt is processed. Challenge expires after 60 seconds or 3 wrong answers.

---

## 20. Failed Login Counter Scope

**Question:** The prompt does not specify whether the 5-failure lockout counter is per-username, per-IP, or per-device.
**Assumption:** Per-username counting prevents targeted account lockout attacks.
**Solution:** Track failed attempts per (username + IP combination). After 5 failures from the same IP for the same username, trigger 15-minute lockout for that combination. Different IPs attempting the same username have independent counters.

---

## 21. Booking State Machine Transitions

**Question:** The prompt lists states (HELD, CONFIRMED, CANCELLED, RELEASED) but does not fully define valid transitions.
**Assumption:** Invalid transitions must be explicitly rejected.
**Solution:** Valid transitions: HELD → CONFIRMED (user confirms), HELD → RELEASED (timeout or user cancel), CONFIRMED → CANCELLED (user/admin cancel), CONFIRMED → RESCHEDULED (creates new HELD with original reference). Invalid: RELEASED → anything, CANCELLED → anything, RESCHEDULED → CONFIRMED without going through HELD.

---

## 22. Hold Expiry Edge Case

**Question:** The prompt says HELD auto-releases after 10 minutes, but does not specify behavior if confirm request arrives at exactly the expiry moment.
**Assumption:** Race conditions must be handled deterministically.
**Solution:** Confirm checks hold_expires_at > current_time with exclusive lock. If expired, return HTTP 410 (Gone) with `HOLD_EXPIRED`. Client must create a new hold. No grace period.

---

## 23. Concurrent Hold Attempts

**Question:** The prompt enforces per-slot quota (default 1) but does not specify what happens when two users try to hold the same slot simultaneously.
**Assumption:** Only one user should succeed; the other should fail immediately.
**Solution:** Use database-level row locking or atomic insert with unique constraint on (resource_id, slot_start, slot_end, state IN (HELD, CONFIRMED)). Second request returns HTTP 409 with `SLOT_UNAVAILABLE`.

---

## 24. Multi-Slot Hold Limits

**Question:** The prompt does not specify whether a user can hold multiple slots simultaneously.
**Assumption:** Unbounded holds could be abused to block availability.
**Solution:** Limit active HELD reservations per user to configurable maximum (default: 3). Exceeding returns HTTP 429 with `MAX_HOLDS_EXCEEDED`.

---

## 25. Slot Template Structure

**Question:** The prompt mentions slot templates with timezone, capacity, buffer_minutes but does not define the schema.
**Assumption:** The structure must support recurring availability patterns.
**Solution:** SlotTemplate includes: resource_id, day_of_week (0-6), start_time (HH:MM), end_time (HH:MM), timezone, capacity (default 1), buffer_minutes (default 5), effective_from (date), effective_until (date nullable). Generate available slots by expanding templates within requested date range.

---

## 26. Buffer Time Application

**Question:** The prompt specifies optional buffer time (default 5 minutes) but does not clarify if buffer applies before, after, or both.
**Assumption:** Buffer interpretation affects conflict detection.
**Solution:** Buffer applies AFTER each booking's end_time. A new booking cannot start until (previous_booking.end_at + buffer_minutes). Example: if booking ends at 10:00 and buffer is 5 min, next booking can start at 10:05 earliest.

---

## 27. Overlap Detection Algorithm

**Question:** The prompt requires conflict detection and oversell protection but does not define the exact overlap algorithm.
**Assumption:** Off-by-one errors in interval comparison cause double-bookings.
**Solution:** Two intervals overlap if: (new_start < existing_end + buffer) AND (new_end > existing_start). Check against all HELD and CONFIRMED reservations for the same resource. Use half-open intervals [start, end) for consistency.

---

## 28. Reschedule Source State Requirement

**Question:** The prompt says reschedules must keep original duration and cannot move to past, but does not specify which states allow rescheduling.
**Assumption:** Only certain states should permit rescheduling.
**Solution:** Only CONFIRMED reservations can be rescheduled. HELD bookings should be cancelled and re-created. Rescheduling creates a new HELD (subject to same 10-min confirm window) and links to original via `rescheduled_from_id`.

---

## 29. Reschedule Past Time Definition

**Question:** The prompt prohibits rescheduling to past time but does not define "past" (server time, user timezone, UTC?).
**Assumption:** Timezone ambiguity causes invalid bookings.
**Solution:** "Past" is defined as: new_start_at < current_server_time_utc. All datetime storage and comparison uses UTC. Display conversion to user timezone is client responsibility.

---

## 30. Idempotency Key Scope

**Question:** The prompt requires idempotency keys for booking mutations with 24-hour window but does not specify if keys are scoped per-user or global.
**Assumption:** Global keys could collide between users.
**Solution:** Idempotency keys are scoped to (user_id, idempotency_key, endpoint). Same key used by different users or on different endpoints are independent. Store: (key_hash, user_id, endpoint, response_body, created_at).

---

## 31. Idempotency Key Reuse Response

**Question:** The prompt does not specify the response when a valid idempotency key is replayed.
**Assumption:** Replay should return the original response, not re-execute.
**Solution:** If idempotency key exists and not expired: return HTTP 200 with exact same response body and header `X-Idempotent-Replayed: true`. Do not re-execute the mutation.

---

## 32. Version Field Initial Value

**Question:** The prompt requires optimistic concurrency with version field but does not specify initial value or increment strategy.
**Assumption:** Version handling must be deterministic.
**Solution:** Version starts at 1 on record creation. Each successful mutation increments version by 1. Client must send current version in request body or header `If-Match`. Mismatch returns HTTP 409 with current version in response for retry.

---

## 33. Content Duplicate Fingerprint Input

**Question:** The prompt specifies SHA-256 of "normalized text/media metadata" for duplicate detection but does not define normalization.
**Assumption:** Different normalization produces different fingerprints, defeating deduplication.
**Solution:** For text content: lowercase, strip whitespace, remove punctuation, sort words alphabetically, then SHA-256. For media: SHA-256 of (file_size + mime_type + duration_seconds + resolution). Store as `duplicate_fingerprint` column.

---

## 34. Duplicate Detection Trigger

**Question:** The prompt says content is "automatically demoted" when duplicate fingerprints match but does not specify when this check runs.
**Assumption:** Check must run at content creation/update time.
**Solution:** On content create/update, compute fingerprint and query for existing items with matching fingerprint (excluding self). If match found AND existing item is not already demoted, mark new item as DUPLICATE_DEMOTED. Do not auto-demote the original.

---

## 35. Rating Threshold Demotion Timing

**Question:** The prompt demotes content when average rating drops below 2.0 after at least 20 ratings, but does not specify when this calculation runs.
**Assumption:** Real-time calculation on every rating could be expensive.
**Solution:** Recalculate average on each new rating submission. If (total_ratings >= 20 AND average_rating < 2.0), set quality_state to RATING_DEMOTED. Cache average_rating and rating_count columns for efficiency.

---

## 36. Content Quality State Enum

**Question:** The prompt references demotion and reinstatement but does not enumerate all quality states.
**Assumption:** Missing states cause logic gaps.
**Solution:** quality_state enum: ACTIVE (normal), DUPLICATE_DEMOTED (fingerprint match), RATING_DEMOTED (avg < 2.0), REPORTED (pending moderation), SUPPRESSED (mod decision), REINSTATED (after appeal). Only ACTIVE content appears in recommendations.

---

## 37. Content Suppression vs Demotion

**Question:** The prompt uses both "demoted" and "excluded from recommendation results" but does not clarify if demoted content is still accessible.
**Assumption:** Demotion visibility rules must be explicit.
**Solution:** DEMOTED content (duplicate/rating) is excluded from recommendations and search results but remains accessible via direct link to the owner or admins. SUPPRESSED content (moderation) is completely hidden from non-admin users.

---

## 38. Moderation Case Lifecycle

**Question:** The prompt mentions reporting, creator appeals, and reviewer decisions but does not define the full state machine.
**Assumption:** Incomplete state machine leads to stuck cases.
**Solution:** ModerationCase states: PENDING (new report), UNDER_REVIEW (assigned to reviewer), DECIDED (reviewer made decision), APPEALED (creator submitted appeal), APPEAL_REVIEWED (final decision after appeal), CLOSED. Transitions: PENDING → UNDER_REVIEW → DECIDED → (CLOSED or APPEALED), APPEALED → APPEAL_REVIEWED → CLOSED.

---

## 39. Who Can Be a Reviewer

**Question:** The prompt references "reviewer decisions" but does not specify which roles can act as reviewers.
**Assumption:** Reviewer role must be explicitly assigned.
**Solution:** Only users with `moderation:review` permission can be assigned as reviewers. By default, platform_admin has this permission. org_admin can be granted it for their organization's content only.

---

## 40. Appeal Submission Rules

**Question:** The prompt allows creator appeals but does not specify constraints (time limit, number of appeals).
**Assumption:** Unbounded appeals create moderation overhead.
**Solution:** Creator can submit one appeal within 7 days of DECIDED state. Appeal must include appeal_notes (min 50 characters). After APPEAL_REVIEWED, no further appeals are allowed.

---

## 41. Learning Event Types

**Question:** The prompt mentions learning behavior and completion analytics but does not enumerate event types.
**Assumption:** Undefined events make analytics meaningless.
**Solution:** LearningEvent event_type enum: STARTED (user opened content), PROGRESS (periodic heartbeat with duration), COMPLETED (user reached completion criteria), PAUSED, RESUMED, ABANDONED (session timeout without completion), ATTEMPT (quiz answer submitted).

---

## 42. Completion Definition

**Question:** The prompt references "completion analytics" but does not define what constitutes completion.
**Assumption:** Different content types have different completion criteria.
**Solution:** Completion rules by content type: video/audio = 90% of duration played, document = reached last page, quiz = submitted all answers. Completion event fires once per (user_id, content_id) pair.

---

## 43. Difficulty Bucket Thresholds

**Question:** The prompt mentions difficulty "bucketed by correct-rate thresholds" but does not specify the thresholds.
**Assumption:** Arbitrary thresholds lead to inconsistent reporting.
**Solution:** Difficulty buckets based on correct rate: EASY (>= 80%), MEDIUM (50-79%), HARD (20-49%), VERY_HARD (< 20%). Recalculate bucket after every 10 new attempts or daily batch, whichever is first.

---

## 44. Analytics Filter Parameters

**Question:** The prompt says analytics are filterable by date range, organization scope, and cohort tags but does not define cohort tag assignment.
**Assumption:** Cohort tags must be defined and assignable.
**Solution:** Cohort tags are arbitrary strings (e.g., "2024-Q1-onboarding", "sales-team") assigned to users via admin API. Analytics endpoints accept `cohort_tags[]` query parameter for filtering. Tags stored in UserCohorts junction table.

---

## 45. CSV Export File Structure

**Question:** The prompt requires offline CSV export to local filesystem but does not specify file naming or directory structure.
**Assumption:** Inconsistent naming causes file management issues.
**Solution:** Export files stored at: `{EXPORT_DIR}/{export_type}/{YYYY-MM-DD}/{user_id}_{parameters_hash}_{timestamp}.csv`. EXPORT_DIR from environment variable. File includes header row with column names.

---

## 46. Export Deduplication Logic

**Question:** The prompt mentions `parameters_hash` in Exports table but does not define deduplication behavior.
**Assumption:** Identical reports should not regenerate.
**Solution:** Before generating export, hash request parameters (report_type, filters, date_range). If matching unexpired export exists (created within last 24 hours), return existing file URL instead of regenerating. Include `X-Export-Cached: true` header.

---

## 47. Export Download Authorization

**Question:** The prompt does not specify who can download generated export files.
**Assumption:** Exports may contain sensitive organization data.
**Solution:** Exports are downloadable only by: the requesting user, org_admin of the same organization scope, or platform_admin. Download endpoint validates requester against export.created_by and export.organization_scope.

---

## 48. Encryption Algorithm and Key Management

**Question:** The prompt requires sensitive fields encrypted at rest using application-managed key but does not specify the algorithm or key derivation.
**Assumption:** Unspecified encryption is unverifiable.
**Solution:** Use AES-256-GCM for field-level encryption. Application key derived from environment variable `ENCRYPTION_MASTER_KEY` using HKDF (SHA-256). Store per-field IV alongside ciphertext. Never log or expose the master key.

---

## 49. Password Hashing Algorithm

**Question:** The prompt mentions password_hash in Users table but does not specify the hashing algorithm.
**Assumption:** Weak hashing fails security requirements.
**Solution:** Use Argon2id with parameters: memory=65536KB, iterations=3, parallelism=4. Store hash as string including algorithm identifier and salt. Verify using constant-time comparison.

---

## 50. Sensitive Field Inventory

**Question:** The prompt lists some sensitive fields (password hashes, tokens, device fingerprints, moderation notes) but may not be exhaustive.
**Assumption:** Missed fields could leak sensitive data.
**Solution:** Complete sensitive field list requiring encryption: password_hash, refresh_token_hash, device_fingerprint, moderation_notes, appeal_notes, audit_before_state, audit_after_state. Fields requiring masking in API responses: device_fingerprint (show last 8 chars), moderation_notes (reviewer-only).

---

## 51. Nightly Backup Schedule and Format

**Question:** The prompt requires nightly local backups with 14-day retention but does not specify the exact time or format.
**Assumption:** Unspecified timing could cause conflicts with active operations.
**Solution:** Backup runs at 02:00 UTC daily via APScheduler. Format: compressed SQLite file copy to `{BACKUP_DIR}/backup_{YYYY-MM-DD_HHMMSS}.sqlite.gz`. Retention job runs immediately after backup to delete files older than 14 days.

---

## 52. Backup Failure Handling

**Question:** The prompt does not specify behavior when backup fails.
**Assumption:** Silent backup failures create undetected data loss risk.
**Solution:** On backup failure: create Alert with type=BACKUP_FAILURE, severity=CRITICAL. Retry backup once after 1 hour. Log error with full exception details. Include backup status in health check endpoint.

---

## 53. Anomaly Alert Types and Thresholds

**Question:** The prompt gives examples (>20 failed logins/hour, repeated booking conflicts) but does not provide a complete list.
**Assumption:** Missing alert types leave security gaps.
**Solution:** Alert types with default thresholds: FAILED_LOGIN_SPIKE (>20/hour per IP or user), BOOKING_CONFLICT_SPIKE (>10 409 responses/hour per user), RATE_LIMIT_ABUSE (>5 429 responses/minute per IP), DEVICE_BLACKLIST_TRIGGER (any new blacklist), SUSPICIOUS_PERMISSION_CHANGE (any permission escalation).

---

## 54. Alert Acknowledgment Workflow

**Question:** The prompt mentions alerts table for administrator review but does not define acknowledgment behavior.
**Assumption:** Unacknowledged alerts pile up without resolution tracking.
**Solution:** Alerts have state: NEW, ACKNOWLEDGED, RESOLVED, FALSE_POSITIVE. Only platform_admin can change state. Acknowledged requires ack_notes. List endpoint supports filtering by state. Auto-archive RESOLVED/FALSE_POSITIVE after 30 days.

---

## 55. Audit Event Required Fields

**Question:** The prompt requires immutable audit events for auth, permission changes, booking mutations, and moderation decisions but does not specify the exact fields.
**Assumption:** Incomplete audit records fail compliance.
**Solution:** AuditEvent fields: id (UUID), event_type, actor_id, actor_role, target_type, target_id, action, before_state (encrypted JSON), after_state (encrypted JSON), ip_address, device_fingerprint, timestamp, request_id. Insert-only table with no UPDATE/DELETE permissions.

---

## 56. Audit Event Types Enumeration

**Question:** The prompt lists categories (auth, permission, booking, moderation) but not specific event types.
**Assumption:** Unclear events lead to inconsistent logging.
**Solution:** event_type enum: AUTH_LOGIN, AUTH_LOGOUT, AUTH_TOKEN_REFRESH, AUTH_FAILED_LOGIN, PERMISSION_GRANT, PERMISSION_REVOKE, PERMISSION_ESCALATION, BOOKING_HOLD, BOOKING_CONFIRM, BOOKING_CANCEL, BOOKING_RESCHEDULE, BOOKING_EXPIRE, MODERATION_REPORT, MODERATION_ASSIGN, MODERATION_DECIDE, MODERATION_APPEAL, MODERATION_APPEAL_DECIDE, CONTENT_CREATE, CONTENT_DEMOTE, CONTENT_REINSTATE.

---

## 57. Timezone Handling Consistency

**Question:** The prompt mentions slot templates have timezone but does not specify how timezone is handled across the system.
**Assumption:** Inconsistent timezone handling causes scheduling errors.
**Solution:** All datetimes stored in UTC. SlotTemplate.timezone specifies display timezone for that resource's availability. Client sends timezone preference in Accept-Timezone header. Server converts to/from UTC on I/O boundaries. API responses include timezone offset in ISO 8601 format.

---

## 58. Rating Update Mechanics

**Question:** The prompt mentions ratings 1-5 but does not specify if users can update their rating or rate only once.
**Assumption:** Rating rules affect average calculation.
**Solution:** Users can rate once per content item. Subsequent submissions update the existing rating. Recalculate average on each create/update. Store rating_count and average_rating as denormalized fields on ContentItem for query efficiency.

---

## 59. Comment Moderation Scope

**Question:** The prompt includes comments as content interaction but does not specify if comments are subject to moderation.
**Assumption:** Unmoderated comments create liability.
**Solution:** Comments follow same moderation flow as content: can be reported, reviewed, suppressed. Comment visibility states mirror content quality states. Suppressed comments show as "[Comment removed by moderator]" placeholder.

---

## 60. Favorites Idempotency

**Question:** The prompt mentions favorites as a metric but does not specify toggle behavior.
**Assumption:** Non-idempotent favorites cause count inconsistencies.
**Solution:** POST /content/{id}/favorite is idempotent: if already favorited, no-op and return success. DELETE /content/{id}/favorite removes favorite. Favorites count on ContentItem updated transactionally with each toggle.

---

## 61. Download Tracking Granularity

**Question:** The prompt tracks downloads as a metric but does not specify what constitutes a download event.
**Assumption:** Download counting must be deterministic.
**Solution:** Download event logged when: GET /content/{id}/download returns HTTP 200. One download counted per (user_id, content_id) per 24-hour period to prevent count inflation from repeated downloads.

---

## 62. API Response Envelope Consistency

**Question:** The prompt does not specify a standard response envelope structure.
**Assumption:** Inconsistent response structures complicate client implementation.
**Solution:** All successful responses use envelope: `{"data": {...}, "meta": {"request_id": "...", "timestamp": "..."}}`. List responses add pagination: `{"data": [...], "meta": {...}, "pagination": {"total": N, "page": P, "per_page": PP, "pages": X}}`. Error responses use: `{"error": {"code": "...", "message": "...", "details": {...}}, "meta": {...}}`.

---

## 63. HTTP Status Code Mapping

**Question:** The prompt does not define exact HTTP status code semantics.
**Assumption:** Inconsistent status codes break client error handling.
**Solution:** Status mapping: 200 (success), 201 (created), 204 (deleted, no body), 400 (validation error), 401 (unauthenticated), 403 (forbidden/blacklisted), 404 (not found), 409 (conflict/version mismatch), 410 (hold expired), 422 (business rule violation), 423 (locked/lockout), 429 (rate limited), 500 (server error).
