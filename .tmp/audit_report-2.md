# Static Audit Report - audit_report-2

## 1. Verdict

- **Overall conclusion: Fail**

## 2. Scope and Static Verification Boundary

- **What was reviewed**: repository documentation and configuration, Flask app entry/middleware wiring, auth/authorization/security modules, booking/content/analytics/audit/admin APIs, SQLAlchemy models/enums, scheduler jobs, and unit/API tests (`README.md`, `docker-compose.yml`, `src/**`, `tests/**`).
- **What was not reviewed**: any generated output under `./.tmp/` (intentionally excluded as evidence), runtime container/network behavior, real TLS termination behavior, real scheduler timing behavior, and filesystem permission behavior at runtime.
- **What was intentionally not executed**: project startup, Docker, tests, migrations, or any runtime requests.
- **Cannot confirm statistically**:
  - End-to-end runtime behavior under real HTTPS termination and request-signing clients.
  - Real scheduler execution cadence in deployed environment.
  - Real concurrency behavior under multi-request contention beyond static locking strategy.

## 3. Repository / Requirement Mapping Summary

- **Prompt core goal mapped**: local multi-org training governance API with auth/tokens/device controls, RBAC + scoped permissions, booking lifecycle with anti-conflict/idempotency/versioning, content governance + moderation/appeals, analytics/exports, audit/alerts, and local backup/security controls.
- **Main implementation areas mapped**:
  - App wiring/middleware: `src/app.py`
  - Domain APIs: `src/api/auth.py`, `permissions.py`, `invitations.py`, `booking.py`, `content.py`, `analytics.py`, `audit.py`, `admin.py`
  - Data model: `src/models/models.py`, `src/models/enums.py`
  - Security primitives: `src/security/*.py`
  - Ops/scheduling: `src/scheduler/__init__.py`, `docker-compose.yml`, `README.md`
  - Static test evidence: `tests/unit/*`, `tests/api/*`, `tests/conftest.py`

## 4. Section-by-section Review

### 4.1 Hard Gates

#### 4.1.1 Documentation and static verifiability
- **Conclusion: Partial Pass**
- **Rationale**: Startup/config/test docs exist and are mostly traceable, but critical security/runtime prerequisites are inconsistent with startup claims.
- **Evidence**:
  - Docs exist: `README.md:24-245`
  - Quick-start claims HTTP service: `README.md:30`
  - TLS enabled by default: `README.md:56`, `docker-compose.yml:53`
  - App rejects non-HTTPS when TLS enabled: `src/app.py:166-176`
  - Gunicorn is started without TLS cert/key configuration: `src/Dockerfile:21`
- **Manual verification note**: Real deployment needs manual validation of TLS termination/proxy setup and request-signing client behavior.

#### 4.1.2 Material deviation from Prompt
- **Conclusion: Fail**
- **Rationale**: Multiple core Prompt constraints are weakened or missing (role model semantics, device blacklist cooldown model, per-identity rate limiting, required data model fields, recommendation exclusion behavior).
- **Evidence**:
  - Token role comes from global `User.role`, not membership role: `src/api/auth.py:245-250`, `src/security/auth_middleware.py:55-85`
  - Invitation redemption updates membership role only: `src/api/invitations.py:269-277`
  - Device model lacks `blacklisted_until`: `src/models/models.py:132-143`
  - Rate limiting enforced only by IP bucket: `src/app.py:197-203`
  - `RATE_LIMIT_BURST` configured but not applied: `src/config/__init__.py:49-50`, `src/app.py:201-202`
  - No recommendation endpoint/flow; no recommendation exclusion logic present.

### 4.2 Delivery Completeness

#### 4.2.1 Core requirement coverage
- **Conclusion: Fail**
- **Rationale**: Many required flows exist, but several explicit core requirements are not fully implemented or are implemented with critical gaps.
- **Evidence**:
  - Booking idempotency + version checks present: `src/api/booking.py:495-525`, `src/api/booking.py:656-684`, `src/api/booking.py:782-810`, `src/api/booking.py:872-908`
  - Hold expiry + release flow present: `src/api/booking.py:697-727`, `src/scheduler/__init__.py:126-157`
  - But reservation hold accepts caller-provided `organization_id` without verifying against resource org or caller membership: `src/api/booking.py:502-510`, `src/api/booking.py:548-585`
  - Required overlap unique constraint not actually overlap-based at DB level (only exact start/end tuple): `src/app.py:252-254`
  - Prompt-required fields missing in model (e.g., membership `data_scope`, permission action/category/assignable, slot timezone/buffer, device cooldown timestamp, learning duration): `src/models/models.py:86-110`, `src/models/models.py:165-175`, `src/models/models.py:132-143`, `src/models/models.py:247-256`

#### 4.2.2 End-to-end deliverable shape
- **Conclusion: Pass**
- **Rationale**: The repository is a coherent multi-module service with docs, APIs, models, scheduler, and tests.
- **Evidence**:
  - Project structure includes app/api/models/security/tests/docs: `README.md:249-312`, `src/api/__init__.py:1-22`, `tests/conftest.py:1-41`

### 4.3 Engineering and Architecture Quality

#### 4.3.1 Structure and module decomposition
- **Conclusion: Pass**
- **Rationale**: Separation by domain modules is clear; middleware, models, scheduler, and utilities are distinct.
- **Evidence**: `src/app.py:41-63`, `src/api/__init__.py:1-22`, `src/security/auth_middleware.py:16-131`, `src/scheduler/__init__.py:14-124`

#### 4.3.2 Maintainability and extensibility
- **Conclusion: Partial Pass**
- **Rationale**: Structure is maintainable, but key authz semantics are tightly coupled to global user role and first-membership token context, limiting multi-org correctness/extensibility.
- **Evidence**:
  - First active membership only in token context: `src/api/auth.py:239-243`, `src/api/auth.py:338-342`
  - Role checks depend on token `role`: `src/security/auth_middleware.py:55-85`
  - Membership context switch endpoint does not issue new token/role context: `src/api/permissions.py:415-455`

### 4.4 Engineering Details and Professionalism

#### 4.4.1 Engineering detail quality (error handling/logging/validation/API design)
- **Conclusion: Partial Pass**
- **Rationale**: Error envelopes/logging/validation are broadly present, but there are material security/detail gaps (sensitive note leakage through audit payloads, incomplete rate-limit requirements).
- **Evidence**:
  - Standardized responses: `src/utils/responses.py:22-86`
  - Global handlers/security headers: `src/app.py:102-140`, `src/app.py:235-243`
  - Moderation notes written into audit `after_state` plaintext: `src/api/content.py:804-808`, `src/api/content.py:921-924`, `src/api/content.py:1015-1019`
  - Audit list returns `before_state`/`after_state` broadly to org_admin: `src/api/audit.py:24-43`, `src/api/audit.py:84-99`

#### 4.4.2 Product-like service shape
- **Conclusion: Partial Pass**
- **Rationale**: Service resembles a real product, but key prompt-critical controls (identity-aware rate limit, device blacklist cooldown state, recommendation exclusion flow) are incomplete.
- **Evidence**:
  - Product-like modules and operational jobs: `src/scheduler/__init__.py:24-120`
  - Missing/partial controls: `src/app.py:197-203`, `src/models/models.py:132-143`

### 4.5 Prompt Understanding and Requirement Fit

#### 4.5.1 Business understanding and fit
- **Conclusion: Fail**
- **Rationale**: Implementation captures much of the surface API scope, but misinterprets crucial requirement semantics (multi-org role/context model, required security controls, and specific data/behavior constraints).
- **Evidence**:
  - Multi-org role semantics drift (global role instead of membership-driven role context): `src/api/auth.py:248`, `src/api/invitations.py:269-277`, `src/security/auth_middleware.py:55-85`
  - Missing required per-identity rate limit + burst behavior: `src/app.py:197-203`, `src/config/__init__.py:49-50`
  - Recommendation exclusion behavior absent.

### 4.6 Aesthetics (frontend-only)

#### 4.6.1 Visual/interaction quality
- **Conclusion: Not Applicable**
- **Rationale**: Repository is backend API-focused; no frontend UI deliverable required here.

## 5. Issues / Suggestions (Severity-Rated)

### Blocker / High

1. **Severity: Blocker**  
   **Title**: TLS requirement conflicts with delivered runtime startup path  
   **Conclusion**: Fail  
   **Evidence**: `README.md:30`, `README.md:56`, `docker-compose.yml:53`, `src/app.py:166-176`, `src/Dockerfile:21`  
   **Impact**: Documented quick-start (`http://localhost:5000`) conflicts with enforced HTTPS gate and no in-container TLS termination configuration; delivery is not statically verifiable as runnable as documented.  
   **Minimum actionable fix**: Either provide actual TLS termination (gunicorn cert/key or reverse proxy service) and update docs, or set `ENABLE_TLS=false` in local default profile and provide separate hardened TLS profile.

2. **Severity: High**  
   **Title**: Reservation hold endpoint lacks organization/resource authorization binding  
   **Conclusion**: Fail  
   **Evidence**: `src/api/booking.py:502-510`, `src/api/booking.py:548-585`  
   **Impact**: Caller controls `organization_id` in hold creation without verification that they belong to that organization and without checking it matches `resource.organization_id`; this enables cross-tenant booking integrity violations and incorrect audit/org attribution.  
   **Minimum actionable fix**: Enforce `resource.organization_id == organization_id` and verify caller org access (membership/platform admin) before creating hold.

3. **Severity: High**  
   **Title**: Membership-role design is not enforced in authorization flow  
   **Conclusion**: Fail  
   **Evidence**: `src/api/auth.py:248`, `src/api/auth.py:239-243`, `src/api/invitations.py:269-277`, `src/security/auth_middleware.py:55-85`  
   **Impact**: Org-scoped role changes through invitations/memberships do not drive `require_role` checks, causing semantic mismatch for org admin capabilities and multi-org governance.  
   **Minimum actionable fix**: Derive effective role from active membership context (or scoped token context), not only global `User.role`, and propagate explicit context switching into token claims.

4. **Severity: High**  
   **Title**: Moderation notes leak through audit event payloads  
   **Conclusion**: Fail  
   **Evidence**: `src/api/content.py:804-808`, `src/api/content.py:921-924`, `src/api/content.py:1015-1019`, `src/api/audit.py:84-99`  
   **Impact**: Decision/appeal notes are stored in plaintext audit JSON and exposed to org-admin readers via `/audit-events`, violating sensitive-field masking expectations.  
   **Minimum actionable fix**: Remove sensitive notes from audit payloads (store redacted references only) or encrypt/redact before persistence and response serialization.

5. **Severity: High**  
   **Title**: Prompt-required rate limiting semantics are not fully implemented  
   **Conclusion**: Fail  
   **Evidence**: `src/app.py:197-203`, `src/config/__init__.py:49-50`, `src/app.py:99`  
   **Impact**: Enforcement is IP-only; per-identity limit and configured burst are not implemented, reducing anti-abuse coverage required by Prompt.  
   **Minimum actionable fix**: Apply dual-bucket checks (IP + identity when authenticated) and incorporate `RATE_LIMIT_BURST` in token bucket capacity.

6. **Severity: High**  
   **Title**: Device blacklist cooldown model is incomplete  
   **Conclusion**: Fail  
   **Evidence**: `src/models/models.py:132-143`, `src/api/auth.py:194-208`, `src/api/auth.py:502-509`  
   **Impact**: No `blacklisted_until`/cooldown timestamp exists; blacklist check is status-only with static retry hint, so configurable cooldown behavior is not representable/enforceable.  
   **Minimum actionable fix**: Add `blacklisted_until` (or equivalent), update blacklist logic to compare current time to cooldown, and include flows to mark high-risk fingerprints.

7. **Severity: High**  
   **Title**: Required overlap-prevention database constraint is weaker than specified  
   **Conclusion**: Partial Fail  
   **Evidence**: `src/app.py:252-254`  
   **Impact**: Unique index only prevents exact `(resource_id,start_time,end_time)` duplicates, not all overlaps; correctness relies on app-layer checks and SQLite write serialization.  
   **Minimum actionable fix**: Implement stronger DB-backed overlap exclusion strategy (or explicit serialized constraint table) consistent with Prompt requirement.

8. **Severity: High**  
   **Title**: Prompt-required sensitive-at-rest encryption coverage is incomplete  
   **Conclusion**: Fail  
   **Evidence**: `src/models/models.py:59`, `src/models/models.py:319`, `src/models/models.py:234-236`, `src/api/auth.py:133`, `src/api/auth.py:499-505`  
   **Impact**: Moderation notes/device fingerprints are protected, but password hashes and token hashes are stored as plain DB text hashes, not encrypted-at-rest as explicitly required.  
   **Minimum actionable fix**: Define field-level encryption policy for all required sensitive fields (or revise requirement docs and acceptance baseline if hashing is intended substitute).

### Medium / Low

1. **Severity: Medium**  
   **Title**: Prompt data model parity gaps  
   **Conclusion**: Partial Fail  
   **Evidence**: `src/models/models.py:86-110`, `src/models/models.py:165-175`, `src/models/models.py:247-256`, `src/models/models.py:276-285`, `src/models/models.py:202-219`  
   **Impact**: Several prompt-specified fields are absent/renamed (e.g., membership `data_scope`, permission action/category/assignable, slot timezone/buffer semantics, learning duration_seconds, suppressed_until), reducing traceability and requirement fidelity.  
   **Minimum actionable fix**: Align schema/API contracts to prompt-required fields and semantics or document explicit justified deviations.

2. **Severity: Medium**  
   **Title**: Test environment bypasses critical middleware controls  
   **Conclusion**: Partial Fail  
   **Evidence**: `tests/conftest.py:10`, `src/app.py:168-169`, `src/app.py:181-182`, `src/app.py:193-194`  
   **Impact**: Request signing, TLS enforcement, and rate limiting are disabled in tests, so major security controls are not statically covered by API tests.  
   **Minimum actionable fix**: Add targeted tests that exercise these controls (at least unit tests for middleware functions and integration tests with testing toggles enabled).

3. **Severity: Low**  
   **Title**: Default bootstrap admin credentials are weak for local default profile  
   **Conclusion**: Risk noted  
   **Evidence**: `README.md:30`, `src/app.py:271-273`  
   **Impact**: Increases accidental insecure deployment risk if defaults are not overridden.  
   **Minimum actionable fix**: Require explicit admin password via env in non-test startup and fail fast if default remains.

## 6. Security Review Summary

- **Authentication entry points: Partial Pass**  
  Evidence: `/auth/register-guest`, `/auth/login`, `/auth/refresh` implemented (`src/api/auth.py:84-383`), token decode/denylist in middleware (`src/security/auth_middleware.py:16-52`).  
  Gap: Tests do not cover signing/TLS/rate-limit middleware controls due testing bypass (`src/app.py:168-194`, `tests/conftest.py:10`).

- **Route-level authorization: Partial Pass**  
  Evidence: Role/permission decorators used broadly (`src/api/admin.py:23-109`, `src/api/invitations.py:28-31`, `src/api/content.py:742-949`).  
  Gap: Effective role semantics depend on global user role, not membership role (`src/api/auth.py:248`, `src/api/invitations.py:269-277`).

- **Object-level authorization: Partial Pass**  
  Evidence: Ownership helper and checks in reservation mutations (`src/security/auth_middleware.py:134-168`, `src/api/booking.py:674-676`, `src/api/booking.py:899-900`).  
  Gap: Hold creation lacks equivalent org/resource binding check (`src/api/booking.py:548-585`).

- **Function-level authorization: Partial Pass**  
  Evidence: Function permissions used for moderation decisions (`src/api/content.py:744`, `src/api/content.py:948`).  
  Gap: Permission model and assignment semantics do not fully match prompt granularity (`src/models/models.py:103-110`).

- **Tenant / user data isolation: Partial Pass**  
  Evidence: Many org-scoped filters exist (`src/api/content.py:276-291`, `src/api/audit.py:40-43`).  
  Gap: Reservation hold can be created with caller-supplied org unrelated to resource (`src/api/booking.py:502-510`, `src/api/booking.py:548-585`).

- **Admin / internal / debug protection: Pass**  
  Evidence: Platform-admin role required and debug endpoints gated by config flag (`src/api/admin.py:70-77`, `src/api/admin.py:106-113`), with redaction support (`src/config/__init__.py:117-132`).

## 7. Tests and Logging Review

- **Unit tests: Partial Pass**  
  Evidence: Unit tests exist for validators/tokens/encryption/passwords/enums/state machine (`tests/unit/*.py`).  
  Gap: No unit coverage for request-signing middleware, rate-limiter behavior boundaries, or TLS enforcement branches.

- **API / integration tests: Partial Pass**  
  Evidence: API suites exist for auth/booking/content/analytics/admin/security (`tests/api/*.py`).  
  Gap: Security middleware (TLS/signing/rate-limit) is bypassed in test mode and not covered (`tests/conftest.py:10`, `src/app.py:168-194`).

- **Logging categories / observability: Pass**  
  Evidence: Structured logger and category/subcategory usage are consistent (`src/logging/__init__.py:35-68`, `src/app.py:213-232`).

- **Sensitive-data leakage risk in logs / responses: Partial Pass**  
  Evidence: Redaction formatter patterns exist (`src/logging/__init__.py:13-32`), moderation notes masked in moderation-case serialization by role (`src/api/content.py:116-134`).  
  Gap: Moderation notes leak through audit payload fields exposed via `/audit-events` (`src/api/content.py:804-808`, `src/api/audit.py:84-99`).

## 8. Test Coverage Assessment (Static Audit)

### 8.1 Test Overview

- **Unit tests exist**: Yes (`tests/unit/*.py`)  
- **API/integration tests exist**: Yes (`tests/api/*.py`)  
- **Frameworks**: `pytest` (`src/requirements.txt:11-12`)  
- **Test entry points**: `run_tests.sh`, direct pytest commands in README (`run_tests.sh:8-25`, `README.md:228-245`)  
- **Documentation for test commands**: Yes (`README.md:228-245`)

### 8.2 Coverage Mapping Table

| Requirement / Risk Point | Mapped Test Case(s) | Key Assertion / Fixture / Mock | Coverage Assessment | Gap | Minimum Test Addition |
|---|---|---|---|---|---|
| Guest register/login/refresh/logout flows | `tests/api/test_auth.py:8-164` | Status assertions for 201/200/204/401 | basically covered | Does not include signed-request enforcement | Add integration tests with signing headers and negative cases for missing/invalid signature |
| Captcha + lockout behavior | `tests/api/test_auth.py:63-94`, `167-229` | Lockout/captcha response codes | partially covered | Lockout test manually mutates DB counter (`test_auth.py:83-87`) instead of full failure progression | Add end-to-end failure progression test without manual counter mutation |
| Booking hold/confirm/cancel/reschedule + idempotency/version | `tests/api/test_booking.py:109-419` | `Idempotency-Key`, `VERSION_CONFLICT`, 410 hold expiry | sufficient | No cross-tenant misuse case for hold organization/resource mismatch | Add test: member from org A attempts hold on org B resource / mismatched organization_id and expect 403 |
| Overlap/conflict handling | `tests/api/test_booking.py:254-327` | `SLOT_UNAVAILABLE` assertions | basically covered | DB-level overlap constraint behavior under race not covered | Add deterministic concurrent simulation/unit test around DB uniqueness and locking strategy |
| Content duplicate/rating/moderation/appeal | `tests/api/test_content.py:49-277` | Duplicate state, moderation decision, appeal flows | basically covered | No tests for recommendation exclusion requirement | Add tests for recommendation endpoint/filter behavior once implemented |
| Cross-org authorization checks | `tests/api/test_security.py:25-187` | 403 on foreign-org create/assign/invite | partially covered | No cross-org check for `/reservations/hold` | Add booking tenant-isolation tests |
| Analytics/export endpoints | `tests/api/test_analytics.py:10-204` | Response schema and export dedupe assertions | partially covered | File-download path is conditional and does not assert robust failure/security branches | Add explicit tests for forbidden cross-org export access and export download ownership constraints |
| Request signing, nonce replay, TLS gate, runtime rate limiting | None | N/A | missing | Critical security controls untested in API suite | Add middleware-level tests for signature validity/replay, TLS-required rejection, and 429 behavior with burst |
| Admin/debug endpoint protections | `tests/api/test_admin.py:16-49` | 403 for member, debug disabled by default, redaction checks | covered | No explicit test for non-platform access to debug when enabled | Add negative test for member on debug endpoints with `ENABLE_DEBUG_ENDPOINTS=true` |

### 8.3 Security Coverage Audit

- **Authentication**: partially covered  
  Covered by auth API tests; signature/TLS/rate-limit middleware paths are not covered.
- **Route authorization**: partially covered  
  Basic 401/403 checks exist; membership-role semantic mismatch is not tested as a failure case.
- **Object-level authorization**: partially covered  
  Reservation ownership transitions tested, but hold-creation tenant binding is not tested.
- **Tenant / data isolation**: partially covered  
  Content/invite/permission isolation tested; booking hold path isolation gap not tested.
- **Admin / internal protection**: covered  
  Admin and debug gating tested.

### 8.4 Final Coverage Judgment

- **Fail**
- **Boundary explanation**:
  - Covered: core happy paths for major APIs, many 401/403/409 branches, booking idempotency/version conflicts.
  - Uncovered high-risk areas: request signing, TLS gate, runtime rate limiting semantics, booking hold tenant-binding misuse, and some prompt-specific security constraints. Current tests could pass while severe production security defects remain.

## 9. Final Notes

- This audit is static-only and evidence-based; runtime-dependent claims are explicitly bounded.
- The repository is substantial and close to product shape, but currently fails acceptance due multiple independent high-severity requirement/security gaps.
- Highest unblock value: fix TLS startup consistency, booking tenant binding, membership-role authorization semantics, moderation-note leakage in audits, and missing rate-limit/device-blacklist requirement fidelity.
