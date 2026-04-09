# Fix Verification Report (Against `.tmp/audit_report-3.md`)

## Scope
- Baseline findings: `.tmp/audit_report-3.md`
- Verification mode: static-only (no runtime execution)
- Reviewed target: `repo/`

## Fix Status Matrix

| Prior Finding | Previous Severity | Current Status | Evidence | Result |
|---|---|---|---|---|
| TLS-required prompt constraint not enforced by default | Blocker | Fixed | `repo/src/config/__init__.py:25`, `repo/docker-compose.yml:56`, `repo/README.md:56` | Default TLS is now enabled and docs/config are aligned. |
| Permission/data-scope not enforced for moderation object-level actions | High | Fixed | `repo/src/security/auth_middleware.py:135`, `repo/src/security/auth_middleware.py:171`, `repo/src/security/auth_middleware.py:271`, `repo/src/api/content.py:829`, `repo/src/api/content.py:867`, `repo/src/api/content.py:1044`, `repo/src/api/content.py:1090` | Moderation endpoints now require org context/role/permission and explicit org-scope verification. |
| Device risk blacklisting flow incomplete (threshold unused) | High | Fixed | `repo/src/config/__init__.py:75`, `repo/src/api/auth.py:69`, `repo/src/api/auth.py:88`, `repo/src/api/auth.py:315` | Risk score increments on failed login with fingerprint and auto-blacklists at threshold. |
| User schema missing `status`/`last_login_at` | High | Fixed | `repo/src/models/models.py:73`, `repo/src/models/models.py:75`, `repo/src/api/auth.py:329`, `repo/src/api/auth.py:381`, `repo/src/api/auth.py:724` | Schema and auth responses now include both fields. |
| Alert thresholds/semantics mismatch (`>20 failed logins/hour`, booking conflict logic) | High | Fixed | `repo/src/api/auth.py:65`, `repo/src/api/auth.py:66`, `repo/src/api/auth.py:132`, `repo/src/scheduler/__init__.py:288`, `repo/src/scheduler/__init__.py:295`, `repo/src/api/booking.py:33`, `repo/src/api/booking.py:56` | Hourly threshold and dedicated booking-conflict event logic are implemented. |
| Buffer-time semantics only globally applied, not per slot/resource | Medium | **Not Fixed** | `repo/src/models/models.py:192`, `repo/src/api/booking.py:137`, `repo/src/api/booking.py:367`, `repo/src/api/booking.py:407` | `SlotTemplate.buffer_minutes` exists but is not accepted/used in overlap calculation; global buffer still drives conflicts. |
| Token-at-rest requirement only partially met (hash-only) | Medium | Fixed | `repo/src/models/models.py:340`, `repo/src/models/models.py:341`, `repo/src/security/tokens.py:97`, `repo/src/api/auth.py:199`, `repo/src/api/auth.py:418` | Refresh token hash is now stored in encrypted column with separate deterministic lookup hash. |
| TLS documentation inconsistency | Low | Fixed | `repo/README.md:56`, `repo/src/config/__init__.py:25`, `repo/docker-compose.yml:56` | Documentation and runtime defaults are consistent. |

## Summary
- Total checked: 8
- Fixed: 7
- Not fixed: 1

## Remaining Open Item
1. **Per-slot/per-resource buffer enforcement remains incomplete**
- Evidence: `repo/src/api/booking.py:137`, `repo/src/api/booking.py:367`, `repo/src/models/models.py:192`
- Minimal fix: accept `buffer_minutes` in slot-template create/update APIs and apply template/resource-specific buffer in overlap checks instead of only `BOOKING_BUFFER_MINUTES`.
