# Fix Verification Report (Against `.tmp/audit_report-3.md`)

## Scope
- Verification target: findings listed in `.tmp/audit_report-3.md`
- Review mode: static-only (no runtime execution, no tests/docker run)
- Codebase reviewed: `repo/` current state

## Issue-by-Issue Fix Check

| Prior Finding | Previous Severity | Current Status | Verification Evidence | Notes |
|---|---|---|---|---|
| TLS-required constraint not enforced by default | Blocker | **Fixed** | `repo/src/config/__init__.py:25`, `repo/docker-compose.yml:56` | `ENABLE_TLS` now defaults to `true` in both config and compose. |
| Permission/data-scope not enforced for moderation object-level actions | High | **Fixed** | `repo/src/security/auth_middleware.py:135`, `repo/src/security/auth_middleware.py:171`, `repo/src/security/auth_middleware.py:271`, `repo/src/api/content.py:829`, `repo/src/api/content.py:867`, `repo/src/api/content.py:1044`, `repo/src/api/content.py:1090` | Added org-context + org-admin + permission checks, plus explicit org-scope verification on moderation actions. |
| Device risk blacklisting flow incomplete | High | **Fixed** | `repo/src/config/__init__.py:75`, `repo/src/api/auth.py:69`, `repo/src/api/auth.py:88`, `repo/src/api/auth.py:315` | Risk accumulation and auto-blacklist threshold logic now implemented and invoked on failed logins with fingerprint. |
| User schema missing `status` / `last_login_at` | High | **Fixed** | `repo/src/models/models.py:73`, `repo/src/models/models.py:75`, `repo/src/api/auth.py:329`, `repo/src/api/auth.py:381`, `repo/src/api/auth.py:724` | Fields now exist and are used in login/profile responses. |
| Alert threshold/semantics mismatch (`>20/hour`, booking conflicts) | High | **Fixed** | `repo/src/api/auth.py:65`, `repo/src/api/auth.py:66`, `repo/src/api/auth.py:132`, `repo/src/scheduler/__init__.py:288`, `repo/src/scheduler/__init__.py:295`, `repo/src/api/booking.py:33`, `repo/src/api/booking.py:56`, `repo/src/api/booking.py:612` | Login spike threshold updated to hourly rule; booking conflict events now use dedicated conflict audit events. |
| Buffer-time semantics only global, not per slot/resource | Medium | **Open** | `repo/src/models/models.py:192`, `repo/src/api/booking.py:367`, `repo/src/api/booking.py:137` | `buffer_minutes` exists in model, but overlap logic still uses global `BOOKING_BUFFER_MINUTES`; slot template API still does not accept/use per-slot buffer. |
| Token-at-rest requirement only partially met (hash-only storage) | Medium | **Open (Partial)** | `repo/src/models/models.py:340`, `repo/src/security/tokens.py:97` | Refresh token material is stored as keyed hash, not encrypted field. Compliance depends on interpretation of “encrypted at rest.” |
| TLS documentation inconsistency | Low | **Fixed** | `repo/README.md:56`, `repo/README.md:194`, `repo/src/config/__init__.py:25`, `repo/docker-compose.yml:56` | README + config + compose are now aligned on TLS default enabled. |

## Summary
- **Fixed:** 6 / 8
- **Open:** 2 / 8
- **Regressions found:** None beyond the two still-open items above.

## Remaining Actions (Minimal)
1. Implement per-slot/per-resource buffer enforcement in booking overlap checks and accept `buffer_minutes` in slot template API payload.
2. Decide token-at-rest compliance policy: either accept keyed hash as compliant or move token hash storage to encrypted field with documented rationale.
