# Fix Verification Report (Against `audit_report-5-fix_check.md`)

## Scope
- Baseline findings: `../.tmp/audit_report-5-fix_check.md`
- Verification mode: static-only (no runtime execution)
- Reviewed target: `repo/`

## Fix Status Matrix

| Prior Finding | Previous Severity | Current Status | Evidence | Result |
|---|---|---|---|---|
| TLS-required prompt constraint not enforced by default | Blocker | Fixed | `src/config/__init__.py:25`, `docker-compose.yml:56`, `README.md:56`, `README.md:195` | TLS remains enabled by default in config/runtime and documentation is consistent with that behavior. |
| Permission/data-scope not enforced for moderation object-level actions | High | Fixed | `src/security/auth_middleware.py:135`, `src/security/auth_middleware.py:171`, `src/security/auth_middleware.py:207`, `src/security/auth_middleware.py:271`, `src/api/content.py:829`, `src/api/content.py:867`, `src/api/content.py:1044`, `src/api/content.py:1090` | Moderation decision endpoints enforce auth + org context + role + permission, plus explicit object org-scope checks. |
| Device risk blacklisting flow incomplete (threshold unused) | High | Fixed | `src/config/__init__.py:74`, `src/config/__init__.py:75`, `src/api/auth.py:69`, `src/api/auth.py:88`, `src/api/auth.py:316` | Failed logins with fingerprint now increase risk score and auto-blacklist at configured threshold. |
| User schema missing `status`/`last_login_at` | High | Fixed | `src/models/models.py:73`, `src/models/models.py:75`, `src/api/auth.py:218`, `src/api/auth.py:331`, `src/api/auth.py:385`, `src/api/auth.py:730` | Schema includes both fields and auth/profile responses expose them. |
| Alert thresholds/semantics mismatch (`>20 failed logins/hour`, booking conflict logic) | High | Fixed | `src/api/auth.py:65`, `src/api/auth.py:132`, `src/scheduler/__init__.py:288`, `src/scheduler/__init__.py:295`, `src/api/booking.py:25`, `src/api/booking.py:55` | Failed-login threshold uses `>20` per hour and booking conflict alerts are driven by dedicated `BOOKING_CONFLICT` events. |
| Buffer-time semantics only globally applied, not per slot/resource | Medium | Fixed | `src/models/models.py:192`, `src/api/booking.py:124`, `src/api/booking.py:139`, `src/api/booking.py:147`, `src/api/booking.py:392`, `src/api/booking.py:443`, `src/api/booking.py:640`, `src/api/booking.py:1022` | Overlap checks now use per-slot-template `buffer_minutes` (with global fallback), and API accepts/validates template-level buffer input. |
| Token-at-rest requirement only partially met (hash-only) | Medium | Fixed | `src/models/models.py:340`, `src/models/models.py:341`, `src/security/tokens.py:97`, `src/api/auth.py:199`, `src/api/auth.py:418` | Refresh token storage uses encrypted at-rest hash plus deterministic lookup hash for indexed retrieval. |
| TLS documentation inconsistency | Low | Fixed | `README.md:56`, `README.md:195`, `src/config/__init__.py:25`, `docker-compose.yml:56` | Docs and runtime defaults are aligned on TLS enabled by default. |

## Summary
- Total checked: 8
- Fixed: 8
- Not fixed: 0

## Remaining Open Items
- None identified in this verification pass.
