# Audit Report 1 - Fix Check

Date: 2026-04-08
Scope: Static code/config/documentation verification against issues listed in `.tmp/audit_report-1.md`.

## Summary
- Fixed: 9
- Partially fixed: 2
- Not fixed: 1

## Issue-by-Issue Status

1. **Request signing and rate limiting controls are not enforced in request path**  
Status: **Fixed**
- `repo/src/app.py:177-209` adds global `before_request` enforcement for request signing and rate limiting (health path exempt only).
- `repo/src/security/signing.py:13-83` verifies timestamp/nonce/signature and stores nonce.
- `repo/src/security/rate_limiter.py:11-89` provides bucket enforcement and headers.

2. **Cross-tenant data access via user-controlled `organization_id` in content listing**  
Status: **Fixed**
- `repo/src/api/content.py:274-277` validates requested org with `_has_org_access`.
- `repo/src/api/content.py:148-159` `_has_org_access` checks platform-admin, token org, or active membership.
- `repo/tests/api/test_security.py:25-77` adds cross-org isolation test coverage.

3. **Cross-tenant content creation without membership/ownership check**  
Status: **Fixed**
- `repo/src/api/content.py:184-188` blocks create when caller lacks org access.
- `repo/tests/api/test_security.py:80-103` validates foreign-org create is denied and own-org create succeeds.

4. **Org-admin privilege escalation in invitation and permission APIs**  
Status: **Fixed**
- `repo/src/api/invitations.py:79-91` requires caller membership in target org unless platform admin.
- `repo/src/api/permissions.py:170-183` and `302-314` enforce same boundary for assign/revoke.
- `repo/tests/api/test_security.py:106-187` includes negative cross-org tests.

5. **Device blacklist matching non-deterministic due encryption randomness**  
Status: **Fixed**
- `repo/src/security/encryption.py:15-24` adds deterministic HMAC lookup hash.
- `repo/src/models/models.py:138` adds `fingerprint_lookup_hash` column.
- `repo/src/api/auth.py:194-201` checks blacklist by deterministic lookup hash.
- `repo/src/api/auth.py:499-505` stores encrypted fingerprint plus deterministic lookup hash at bind.

6. **Permission-gated endpoints unreachable from normal login flow**  
Status: **Fixed**
- `repo/src/api/auth.py:243-251` login now injects DB-derived permission codes into access token.
- `repo/src/api/auth.py:342-350` refresh path does the same.
- `repo/src/security/auth_middleware.py:47` reads `permissions` claim into `g.current_user`.
- `repo/tests/api/test_content.py:30-33` explicitly documents and tests real login-based permission propagation.

7. **Moderation notes encryption/masking not implemented**  
Status: **Fixed**
- `repo/src/models/models.py:27-47` introduces `EncryptedText` type with AES-GCM at rest.
- `repo/src/models/models.py:234-236` moderation note fields use `EncryptedText`.
- `repo/src/api/content.py:116-129` role-based note masking in serializer.

8. **Oversell protection lacks DB-level overlap constraint; race-prone logic**  
Status: **Not fixed**
- `repo/src/api/booking.py:125-135` still uses read/check overlap query (`with_for_update`) and count.
- `repo/src/api/booking.py:565-574` still application-level quota/overlap decision before insert.
- `repo/src/models/models.py:180-200` no DB exclusion/overlap constraint present on reservations.

9. **TLS required by prompt but disabled by default and not enforced**  
Status: **Partially fixed**
- Fixed in runtime config/deployment:
  - `repo/src/config/__init__.py:25` default `ENABLE_TLS=True`.
  - `repo/docker-compose.yml:53` sets `ENABLE_TLS=true`.
  - `repo/src/app.py:165-175` rejects non-HTTPS when TLS enabled.
- Remaining mismatch:
  - `repo/README.md:187` still documents `ENABLE_TLS` default as `false`.

10. **Prompt-default operational values diverge (backup retention, device cooldown)**  
Status: **Partially fixed**
- Fixed in config/deployment:
  - `repo/src/config/__init__.py:75` cooldown default `168` hours (7 days).
  - `repo/src/config/__init__.py:83` backup retention default `14` days.
  - `repo/docker-compose.yml:43` and `:46` match these values.
- Remaining mismatch:
  - `repo/README.md:147` still says `24` hours.
  - `repo/README.md:160` still says `30` days.

11. **Documentation references non-delivered evidence files and incorrect coverage target**  
Status: **Partially fixed**
- Coverage target fixed in script:
  - `repo/run_tests.sh:24` now uses `--cov=src`.
- Remaining issues:
  - `repo/README.md:244` still shows `--cov=backend`.
  - `repo/README.md:306-311` references docs not present under `repo/docs` (checked available docs are only root `docs/api-spec.md`, `docs/design.md`, `docs/questions.md`).

12. **Prompt-specified anomaly alerts missing beyond backup failure**  
Status: **Fixed**
- Failed-login spike alerting:
  - `repo/src/api/auth.py:47-77` and `225-226` check/login-failure thresholds and create alerts.
  - `repo/src/scheduler/__init__.py:288-307` periodic anomaly evaluation for failed login spikes.
- Booking-conflict spike alerting:
  - `repo/src/api/booking.py:24-55` conflict threshold alert helper.
  - `repo/src/api/booking.py:569` triggers conflict-spike check on slot conflict.

## Overall Verdict
**Partial Pass**

The majority of critical security and tenant-isolation defects from the previous audit are fixed. Remaining acceptance blockers are:
- Missing DB-level overlap protection for reservations (race-hardening still incomplete).
- Documentation inconsistencies and missing referenced evidence docs.
- README defaults not aligned with updated runtime defaults for TLS/cooldown/backup retention.
