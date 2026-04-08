# Static Audit Report

## 1. Verdict
- **Overall conclusion: Fail**

## 2. Scope and Static Verification Boundary
- **Reviewed:** `README.md`, Docker/config files, Flask app factory/middleware, API modules (`auth`, `permissions`, `invitations`, `booking`, `content`, `analytics`, `audit`, `admin`, `health`), models/enums/security utilities, scheduler, and all `tests/unit` + `tests/api` files.
- **Not reviewed/executed:** runtime behavior, live HTTP server behavior, Docker runtime behavior, DB lock behavior under true concurrency, real TLS termination behavior, cron timing behavior.
- **Intentionally not executed:** project startup, tests, Docker, external services.
- **Manual verification required:** runtime TLS enforcement behind reverse proxy, scheduler timing reliability, true concurrent booking races on deployed SQLite volume, filesystem permissions for export/backup directories.

## 3. Repository / Requirement Mapping Summary
- **Prompt core goal:** offline multi-org training center API with local auth, scoped authorization, booking governance (holds/idempotency/concurrency), content moderation/governance, analytics/export, and security controls.
- **Mapped implementation areas:** Flask blueprints, SQLAlchemy schema, auth/token/device/security middleware, reservation state machine/idempotency/overlap handling, moderation pipelines, analytics/export pipeline, audit/alerts/scheduler, and static test suite.
- **Result:** large functional surface exists, but several explicit prompt/security requirements are partially implemented or violated.

## 4. Section-by-section Review

### 1. Hard Gates
#### 1.1 Documentation and static verifiability
- **Conclusion: Partial Pass**
- **Rationale:** README provides run/config/test instructions and route inventory, and code structure is discoverable. However, security/TLS defaults are contradictory between docs and executable config.
- **Evidence:** `README.md:56`, `README.md:194`, `src/config/__init__.py:25`, `docker-compose.yml:55`, `src/app.py:170`
- **Manual verification note:** Runtime behavior under `docker-compose.tls.yml` still requires manual check.

#### 1.2 Material deviation from Prompt
- **Conclusion: Fail**
- **Rationale:** Several prompt-critical security/governance semantics are not fully enforced (TLS local requirement, permission scope/object authorization gaps, device-risk blacklisting automation, schema parity gaps).
- **Evidence:** `src/config/__init__.py:25`, `src/api/content.py:827`, `src/security/auth_middleware.py:134`, `src/config/__init__.py:74`, `src/models/models.py:64`

### 2. Delivery Completeness
#### 2.1 Core requirement coverage
- **Conclusion: Partial Pass**
- **Rationale:** Core APIs exist for auth, invitations, booking lifecycle, moderation, analytics, exports, audit/alerts. But explicit requirements are partially unmet: missing user `status` enum/`last_login_at`, weak permission data-scope enforcement, and incomplete device-risk blacklisting flow.
- **Evidence:** `src/api/auth.py:180`, `src/api/booking.py:488`, `src/api/content.py:745`, `src/api/analytics.py:208`, `src/models/models.py:64`, `src/config/__init__.py:74`

#### 2.2 End-to-end 0->1 deliverable
- **Conclusion: Pass**
- **Rationale:** Repo has coherent app structure, Docker/build config, models, routes, and substantial tests.
- **Evidence:** `README.md:1`, `src/app.py:17`, `src/models/models.py:64`, `tests/api/test_auth.py:7`, `tests/api/test_booking.py:47`

### 3. Engineering and Architecture Quality
#### 3.1 Structure and modular decomposition
- **Conclusion: Pass**
- **Rationale:** Domain split is clear (API/security/models/scheduler/utils/tests) and avoids single-file monolith.
- **Evidence:** `src/api/__init__.py:2`, `src/security/auth_middleware.py:13`, `src/models/models.py:64`, `src/scheduler/__init__.py:14`

#### 3.2 Maintainability/extensibility
- **Conclusion: Partial Pass**
- **Rationale:** Extensible in many areas, but important policy semantics are encoded inconsistently (e.g., permission scope model exists but enforcement is shallow).
- **Evidence:** `src/models/models.py:123`, `src/security/auth_middleware.py:134`, `src/api/permissions.py:46`

### 4. Engineering Details and Professionalism
#### 4.1 Error handling, logging, validation, API design
- **Conclusion: Partial Pass**
- **Rationale:** Good envelope consistency/logging and many validations exist. Significant policy correctness issues remain in security/alert semantics.
- **Evidence:** `src/utils/responses.py:22`, `src/app.py:102`, `src/logging/__init__.py:13`, `src/api/auth.py:64`, `src/api/booking.py:37`

#### 4.2 Product-level professionalism
- **Conclusion: Partial Pass**
- **Rationale:** Service shape is production-like, but several high-severity security/governance requirements are not fully met.
- **Evidence:** `src/app.py:17`, `src/api/admin.py:23`, `src/api/content.py:827`

### 5. Prompt Understanding and Requirement Fit
#### 5.1 Business understanding and fit
- **Conclusion: Fail**
- **Rationale:** Core scenario is mostly understood, but key constraints are weakened (TLS in local deployments, authorization data-scope semantics, blacklisting automation, schema fidelity).
- **Evidence:** `src/config/__init__.py:25`, `docker-compose.yml:55`, `src/security/auth_middleware.py:134`, `src/models/models.py:64`, `src/config/__init__.py:74`

### 6. Aesthetics (frontend-only/full-stack only)
#### 6.1 Visual/interaction quality
- **Conclusion: Not Applicable**
- **Rationale:** Repository is backend API service with no frontend UI deliverable.
- **Evidence:** `src/app.py:17`, `src/api/__init__.py:2`

## 5. Issues / Suggestions (Severity-Rated)

### Blocker / High
1. **Severity: Blocker**
- **Title:** TLS-required prompt constraint is not enforced by default
- **Conclusion:** Fail
- **Evidence:** `src/config/__init__.py:25`, `docker-compose.yml:55`, `src/app.py:170`, `README.md:194`
- **Impact:** Deployment can run non-TLS despite prompt requiring TLS even local, weakening transport security.
- **Minimum actionable fix:** Set `ENABLE_TLS` default true, align compose defaults, and keep explicit opt-out only for test harness with documented exception.

2. **Severity: High**
- **Title:** Permission/data-scope model is not enforced for object-level moderation actions
- **Conclusion:** Fail
- **Evidence:** `src/security/auth_middleware.py:134`, `src/security/auth_middleware.py:147`, `src/api/content.py:827`, `src/api/content.py:1031`, `src/models/models.py:123`
- **Impact:** A user with `moderation:review` can operate on moderation cases/content without explicit organization-scope validation.
- **Minimum actionable fix:** Enforce org/object scope checks in moderation decision/appeal-decision handlers and extend `require_permission` to validate scoped grants.

3. **Severity: High**
- **Title:** Device risk blacklisting flow is incomplete (threshold configured but unused)
- **Conclusion:** Fail
- **Evidence:** `src/config/__init__.py:74`, `src/api/auth.py:545`, `src/api/auth.py:234`
- **Impact:** Requirement for repeated high-risk fingerprint blacklisting is not implemented; only pre-blacklisted devices are blocked.
- **Minimum actionable fix:** Implement risk-score accumulation and automatic blacklist transition when threshold is exceeded, including cooldown and audit event.

4. **Severity: High**
- **Title:** User schema deviates from explicit Prompt fields
- **Conclusion:** Fail
- **Evidence:** `src/models/models.py:64`, `src/models/models.py:72`, `src/models/models.py:73`
- **Impact:** Missing `status` enum and `last_login_at` limits compliance/reporting fidelity and requirement traceability.
- **Minimum actionable fix:** Add `status` enum + `last_login_at` to `User`, migrate schema, and update auth flows/tests.

5. **Severity: High**
- **Title:** Alert thresholds/semantics deviate from required anomaly rules
- **Conclusion:** Fail
- **Evidence:** `src/api/auth.py:64`, `src/scheduler/__init__.py:289`, `src/api/booking.py:37`
- **Impact:** Alerting logic does not match required `>20 failed logins/hour`; booking conflict alert currently counts held reservations, not conflicts.
- **Minimum actionable fix:** Implement explicit hourly failed-login threshold and conflict-event-based booking anomaly counters.

### Medium / Low
6. **Severity: Medium**
- **Title:** Buffer-time semantics are only globally applied, not per slot/resource
- **Conclusion:** Partial Fail
- **Evidence:** `src/models/models.py:190`, `src/api/booking.py:120`, `src/api/booking.py:338`
- **Impact:** Prompt’s per-slot optional buffer behavior is only partially represented.
- **Minimum actionable fix:** Accept/store `buffer_minutes` in slot template API and use it in overlap checks.

7. **Severity: Medium**
- **Title:** Token-at-rest requirement is only partially met by hashing
- **Conclusion:** Partial Fail
- **Evidence:** `src/models/models.py:338`, `src/security/tokens.py:97`
- **Impact:** Stored token material is hashed (good), but strict “encrypted at rest” requirement may still be unmet.
- **Minimum actionable fix:** Clarify requirement acceptance for keyed-hash storage or move token hash field to encrypted type with key rotation handling.

8. **Severity: Low**
- **Title:** Documentation claims around TLS defaults are inconsistent
- **Conclusion:** Fail
- **Evidence:** `README.md:56`, `README.md:194`, `src/config/__init__.py:25`, `docker-compose.yml:55`
- **Impact:** Reviewer/operator confusion and misconfiguration risk.
- **Minimum actionable fix:** Align README default tables and narrative with actual config defaults.

## 6. Security Review Summary
- **Authentication entry points:** **Partial Pass**
  - Evidence: `src/api/auth.py:101`, `src/api/auth.py:180`, `src/security/tokens.py:13`
  - Reasoning: Local username/password auth, refresh rotation, lockout/captcha exist; schema/blacklisting gaps remain.

- **Route-level authorization:** **Partial Pass**
  - Evidence: `src/security/auth_middleware.py:16`, `src/security/auth_middleware.py:55`, `src/api/admin.py:25`
  - Reasoning: Decorators are widely used, but some sensitive actions rely only on code-level permission without scope checks.

- **Object-level authorization:** **Fail**
  - Evidence: `src/security/auth_middleware.py:178`, `src/api/content.py:827`, `src/api/content.py:1031`
  - Reasoning: Object ownership helper exists but is not applied to moderation decision endpoints.

- **Function-level authorization:** **Partial Pass**
  - Evidence: `src/security/auth_middleware.py:134`, `src/api/content.py:829`
  - Reasoning: Permission checks exist but do not evaluate data-scope constraints.

- **Tenant / user data isolation:** **Partial Pass**
  - Evidence: `src/api/content.py:185`, `src/api/booking.py:561`, `src/api/analytics.py:41`
  - Reasoning: Many org-scope checks exist; moderation path still has cross-org risk.

- **Admin / internal / debug protection:** **Pass**
  - Evidence: `src/api/admin.py:25`, `src/api/admin.py:76`, `src/config/__init__.py:95`
  - Reasoning: Platform-admin gating + debug feature flag are enforced.

## 7. Tests and Logging Review
- **Unit tests:** **Pass (static presence)**
  - Evidence: `tests/unit/test_middleware_controls.py:1`, `tests/unit/test_tokens.py:22`, `tests/unit/test_encryption.py:10`
- **API/integration tests:** **Pass (static presence), Partial for risk closure**
  - Evidence: `tests/api/test_auth.py:7`, `tests/api/test_booking.py:108`, `tests/api/test_content.py:194`
- **Logging categories/observability:** **Pass**
  - Evidence: `src/logging/__init__.py:35`, `src/app.py:238`, `src/api/booking.py:639`
- **Sensitive leakage risk in logs/responses:** **Partial Pass**
  - Evidence: `src/logging/__init__.py:13`, `src/api/content.py:128`, `src/api/audit.py:22`
  - Note: Redaction exists, but confirmation of all sensitive variants under runtime payload diversity requires manual verification.

## 8. Test Coverage Assessment (Static Audit)

### 8.1 Test Overview
- Unit tests exist: **Yes** (`tests/unit/*.py`)
- API/integration tests exist: **Yes** (`tests/api/*.py`)
- Framework: **pytest** (`run_tests.sh:10`, `run_tests.sh:15`)
- Test entry points documented: **Yes** (`README.md:237`, `README.md:243`)
- Coverage command documented: **Yes** (`README.md:249`)

### 8.2 Coverage Mapping Table
| Requirement / Risk Point | Mapped Test Case(s) | Key Assertion / Fixture / Mock | Coverage Assessment | Gap | Minimum Test Addition |
|---|---|---|---|---|---|
| Access/refresh token lifecycle | `tests/api/test_auth.py:36`, `tests/api/test_auth.py:98` | token presence + refresh success | sufficient | None major | Add refresh-token device binding tests if implemented |
| Captcha/lockout controls | `tests/api/test_auth.py:168`, `tests/api/test_auth.py:63` | CAPTCHA_REQUIRED and lockout 423 | basically covered | Lockout currently partly forced via DB mutation | Add pure API-only lockout progression test |
| Booking hold/confirm/cancel/reschedule | `tests/api/test_booking.py:109`, `tests/api/test_booking.py:126`, `tests/api/test_booking.py:210` | state transitions + version handling | sufficient | None major | Add concurrent double-confirm race test (manual/synthetic) |
| Idempotency and replay headers | `tests/api/test_booking.py:331` | same key => replay + header | sufficient | No negative test for changed payload same key | Add mismatched-payload same-key behavior test |
| Overlap/oversell protection | `tests/api/test_booking.py:254`, `tests/api/test_booking.py:284`, `tests/api/test_prompt_compliance.py:800` | conflict 409 + trigger guard | sufficient | True runtime concurrency still unproven | Add transactional contention test harness |
| Cross-org isolation (content/invitations/permissions) | `tests/api/test_security.py:26`, `tests/api/test_security.py:107`, `tests/api/test_security.py:146` | 403 on cross-org operations | basically covered | Moderation cross-org scope not tested | Add cross-org moderation-decision denial test |
| Moderation workflow and appeals | `tests/api/test_content.py:215`, `tests/api/test_content.py:242` | suppress/appeal/reinstate path | basically covered | No org-scope test for reviewer permissions | Add scoped-permission moderation tests |
| Analytics + exports basics | `tests/api/test_analytics.py:10`, `tests/api/test_analytics.py:138` | analytics response fields + export creation | basically covered | Missing tests for cohort filters on all analytics endpoints and auth boundaries | Add cohort filter + forbidden org export tests |
| TLS/request-signing/rate-limiter middleware | `tests/unit/test_middleware_controls.py:54`, `tests/unit/test_middleware_controls.py:101`, `tests/unit/test_middleware_controls.py:229` | direct middleware function assertions | basically covered | Not integrated through full prod stack | Add integration test with non-testing app + signed requests |
| Alert/anomaly semantics | `tests/api/test_audit.py:39` | generic alert lifecycle only | insufficient | Required thresholds/logic not asserted | Add tests for >20/hour failed-login and booking-conflict anomaly semantics |

### 8.3 Security Coverage Audit
- **Authentication:** basically covered (`tests/api/test_auth.py:36`, `tests/unit/test_tokens.py:22`), but device-binding/blacklist-threshold behavior is not fully validated.
- **Route authorization:** basically covered (`tests/api/test_security.py:20`, `tests/api/test_admin.py:16`).
- **Object-level authorization:** insufficient; moderation object/org scope tests are missing (`tests/api/test_content.py:215` covers happy path only).
- **Tenant/data isolation:** partially covered (`tests/api/test_security.py:26`), but not across all privileged flows.
- **Admin/internal protection:** covered (`tests/api/test_admin.py:29`, `tests/api/test_admin.py:34`).

### 8.4 Final Coverage Judgment
- **Partial Pass**
- Major happy paths and several security basics are covered, but severe defects could still pass due to missing tests for scoped moderation authorization, alert-threshold semantics, and some policy-level prompt constraints.

## 9. Final Notes
- The repository is substantial and not a toy demo, but hard security/compliance constraints from the prompt are not fully satisfied.
- The highest-priority fixes are TLS-default enforcement, scoped authorization correctness, device-risk blacklisting automation, and anomaly rule correctness.
