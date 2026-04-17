# Test Coverage Audit

## Scope and Method

- Mode: static inspection only (no test execution, no runtime verification).
- Inspected areas: `repo/src/api`, `repo/src/app.py`, `repo/tests/api`, `repo/tests/unit`, `repo/run_tests.sh`, `repo/README.md`.

## Project Type Detection

- Declared in README: `Project Type: backend` (`repo/README.md:1`).
- Inference check: backend-only Flask API structure; no frontend code artifacts detected (`repo/src/app.py`, `repo/src/api/*`, absence of frontend manifests/files).
- Final type used for audit: `backend`.

## Backend Endpoint Inventory

Resolved from Flask route decorators (`repo/src/api/*.py`) including blueprint prefixes:

1. `POST /auth/register-guest`
2. `POST /auth/login`
3. `POST /auth/refresh`
4. `POST /auth/logout`
5. `POST /auth/logout-all`
6. `POST /auth/device/bind`
7. `POST /auth/device/unbind`
8. `GET /auth/me`
9. `GET /audit-events`
10. `GET /alerts`
11. `POST /alerts/:alert_id/ack`
12. `POST /alerts/:alert_id/resolve`
13. `GET /permissions`
14. `POST /permissions`
15. `POST /permissions/assign`
16. `POST /permissions/revoke`
17. `GET /permissions/memberships`
18. `POST /permissions/memberships/switch-context`
19. `GET /analytics/learning-behavior`
20. `GET /analytics/completion`
21. `GET /analytics/wrong-answers`
22. `GET /analytics/difficulty`
23. `GET /analytics/course-effectiveness`
24. `POST /exports`
25. `GET /exports`
26. `GET /exports/:export_id/download`
27. `POST /invitations`
28. `GET /invitations`
29. `POST /invitations/redeem`
30. `POST /invitations/revoke`
31. `POST /content`
32. `GET /content`
33. `GET /content/recommendations`
34. `POST /content/:content_id/ratings`
35. `POST /content/:content_id/comments`
36. `POST /content/:content_id/favorite`
37. `DELETE /content/:content_id/favorite`
38. `POST /content/:content_id/download`
39. `POST /content/:content_id/report`
40. `POST /moderation/cases/:case_id/decision`
41. `POST /moderation/cases/:case_id/appeal`
42. `POST /moderation/cases/:case_id/appeal-decision`
43. `POST /resources`
44. `GET /resources`
45. `POST /slot-templates`
46. `GET /availability`
47. `POST /reservations/hold`
48. `POST /reservations/:reservation_id/confirm`
49. `POST /reservations/:reservation_id/cancel`
50. `POST /reservations/:reservation_id/reschedule`
51. `GET /reservations`
52. `GET /admin/system-status`
53. `GET /admin/debug/routes`
54. `GET /admin/debug/config-redacted`
55. `GET /health`

Route evidence: `repo/src/api/auth.py:153,236,401,496,548,595,652,696`; `repo/src/api/audit.py:44,137,206,268`; `repo/src/api/permissions.py:28,82,159,291,388,431`; `repo/src/api/analytics.py:208,261,385,465,550,647,754,791`; `repo/src/api/invitations.py:29,158,225,355`; `repo/src/api/content.py:166,260,348,432,554,607,662,695,745,827,926,1042`; `repo/src/api/booking.py:273,330,376,461,536,718,844,934,1099`; `repo/src/api/admin.py:23,70,106`; `repo/src/api/health.py:19`.

## API Test Mapping Table

| Endpoint                                        | Covered | Test Type         | Test Files                                                         | Evidence                                                                                                                  |
| ----------------------------------------------- | ------- | ----------------- | ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------- |
| POST /auth/register-guest                       | yes     | true no-mock HTTP | `tests/api/test_auth.py`                                           | `TestRegisterGuest.test_register_guest_success` (`repo/tests/api/test_auth.py:8`)                                         |
| POST /auth/login                                | yes     | true no-mock HTTP | `tests/api/test_auth.py`                                           | `TestLogin.test_login_success` (`repo/tests/api/test_auth.py:36`)                                                         |
| POST /auth/refresh                              | yes     | true no-mock HTTP | `tests/api/test_auth.py`                                           | `TestRefreshToken.test_refresh_token_success` (`repo/tests/api/test_auth.py:104`)                                         |
| POST /auth/logout                               | yes     | true no-mock HTTP | `tests/api/test_auth.py`                                           | `TestLogout.test_logout_success` (`repo/tests/api/test_auth.py:135`)                                                      |
| POST /auth/logout-all                           | yes     | true no-mock HTTP | `tests/api/test_auth.py`                                           | `TestLogout.test_logout_all_revokes_tokens` (`repo/tests/api/test_auth.py:154`)                                           |
| POST /auth/device/bind                          | yes     | true no-mock HTTP | `tests/api/test_auth.py`                                           | `TestDevice.test_device_bind` (`repo/tests/api/test_auth.py:269`)                                                         |
| POST /auth/device/unbind                        | yes     | true no-mock HTTP | `tests/api/test_auth.py`                                           | `TestDevice.test_device_unbind` (`repo/tests/api/test_auth.py:280`)                                                       |
| GET /auth/me                                    | yes     | true no-mock HTTP | `tests/api/test_auth.py`, `tests/api/test_security.py`             | `TestMe.test_get_me` (`repo/tests/api/test_auth.py:244`)                                                                  |
| GET /audit-events                               | yes     | true no-mock HTTP | `tests/api/test_audit.py`                                          | `TestAuditEvents.test_list_audit_events` (`repo/tests/api/test_audit.py:22`)                                              |
| GET /alerts                                     | yes     | true no-mock HTTP | `tests/api/test_audit.py`                                          | `TestAlerts.test_list_alerts` (`repo/tests/api/test_audit.py:50`)                                                         |
| POST /alerts/:alert_id/ack                      | yes     | true no-mock HTTP | `tests/api/test_audit.py`                                          | `TestAlerts.test_alert_lifecycle` (`repo/tests/api/test_audit.py:56`)                                                     |
| POST /alerts/:alert_id/resolve                  | yes     | true no-mock HTTP | `tests/api/test_audit.py`                                          | `TestAlerts.test_alert_lifecycle` (`repo/tests/api/test_audit.py:56`)                                                     |
| GET /permissions                                | yes     | true no-mock HTTP | `tests/api/test_permissions.py`                                    | `TestPermissions.test_list_permissions` (`repo/tests/api/test_permissions.py:29`)                                         |
| POST /permissions                               | yes     | true no-mock HTTP | `tests/api/test_permissions.py`                                    | `TestPermissions.test_create_permission_as_admin` (`repo/tests/api/test_permissions.py:8`)                                |
| POST /permissions/assign                        | yes     | true no-mock HTTP | `tests/api/test_permissions.py`                                    | `TestPermissions.test_assign_permission` (`repo/tests/api/test_permissions.py:41`)                                        |
| POST /permissions/revoke                        | yes     | true no-mock HTTP | `tests/api/test_permissions.py`                                    | `TestPermissions.test_revoke_permission` (`repo/tests/api/test_permissions.py:59`)                                        |
| GET /permissions/memberships                    | yes     | true no-mock HTTP | `tests/api/test_permissions.py`                                    | `TestMemberships.test_list_memberships` (`repo/tests/api/test_permissions.py:84`)                                         |
| POST /permissions/memberships/switch-context    | yes     | true no-mock HTTP | `tests/api/test_prompt_compliance.py`                              | `TestSwitchContextReissuesTokens.test_switch_context_returns_new_tokens` (`repo/tests/api/test_prompt_compliance.py:158`) |
| GET /analytics/learning-behavior                | yes     | true no-mock HTTP | `tests/api/test_analytics.py`                                      | `TestLearningBehavior.test_learning_behavior` (`repo/tests/api/test_analytics.py:10`)                                     |
| GET /analytics/completion                       | yes     | true no-mock HTTP | `tests/api/test_analytics.py`                                      | `TestCompletionAnalytics.test_completion_analytics` (`repo/tests/api/test_analytics.py:38`)                               |
| GET /analytics/wrong-answers                    | yes     | true no-mock HTTP | `tests/api/test_analytics.py`                                      | `TestWrongAnswers.test_wrong_answers` (`repo/tests/api/test_analytics.py:138`)                                            |
| GET /analytics/difficulty                       | yes     | true no-mock HTTP | `tests/api/test_analytics.py`                                      | `TestDifficultyAnalytics.test_difficulty_analytics` (`repo/tests/api/test_analytics.py:85`)                               |
| GET /analytics/course-effectiveness             | yes     | true no-mock HTTP | `tests/api/test_analytics.py`                                      | `TestCourseEffectiveness.test_course_effectiveness` (`repo/tests/api/test_analytics.py:196`)                              |
| POST /exports                                   | yes     | true no-mock HTTP | `tests/api/test_analytics.py`                                      | `TestExports.test_create_export` (`repo/tests/api/test_analytics.py:248`)                                                 |
| GET /exports                                    | yes     | true no-mock HTTP | `tests/api/test_analytics.py`                                      | `TestExports.test_list_exports` (`repo/tests/api/test_analytics.py:279`)                                                  |
| GET /exports/:export_id/download                | yes     | true no-mock HTTP | `tests/api/test_analytics.py`                                      | `TestExports.test_download_export` (`repo/tests/api/test_analytics.py:295`)                                               |
| POST /invitations                               | yes     | true no-mock HTTP | `tests/api/test_invitations.py`                                    | `TestInvitations.test_create_invitation` (`repo/tests/api/test_invitations.py:32`)                                        |
| GET /invitations                                | yes     | true no-mock HTTP | `tests/api/test_invitations.py`                                    | `TestInvitations.test_list_invitations` (`repo/tests/api/test_invitations.py:88`)                                         |
| POST /invitations/redeem                        | yes     | true no-mock HTTP | `tests/api/test_invitations.py`                                    | `TestInvitations.test_redeem_invitation` (`repo/tests/api/test_invitations.py:38`)                                        |
| POST /invitations/revoke                        | yes     | true no-mock HTTP | `tests/api/test_invitations.py`                                    | `TestInvitations.test_revoke_invitation` (`repo/tests/api/test_invitations.py:123`)                                       |
| POST /content                                   | yes     | true no-mock HTTP | `tests/api/test_content.py`                                        | `TestContentCreation.test_create_content` (`repo/tests/api/test_content.py:49`)                                           |
| GET /content                                    | yes     | true no-mock HTTP | `tests/api/test_content.py`                                        | `TestContentCreation.test_list_content` (`repo/tests/api/test_content.py:60`)                                             |
| GET /content/recommendations                    | yes     | true no-mock HTTP | `tests/api/test_content.py`, `tests/api/test_prompt_compliance.py` | `TestContentRecommendations.test_recommendations_returns_items_with_fields` (`repo/tests/api/test_content.py:195`)        |
| POST /content/:content_id/ratings               | yes     | true no-mock HTTP | `tests/api/test_content.py`                                        | `TestContentRating.test_rate_content` (`repo/tests/api/test_content.py:99`)                                               |
| POST /content/:content_id/comments              | yes     | true no-mock HTTP | `tests/api/test_content.py`                                        | `TestContentComment.test_comment_on_content` (`repo/tests/api/test_content.py:121`)                                       |
| POST /content/:content_id/favorite              | yes     | true no-mock HTTP | `tests/api/test_content.py`                                        | `TestContentFavorite.test_favorite_content` (`repo/tests/api/test_content.py:140`)                                        |
| DELETE /content/:content_id/favorite            | yes     | true no-mock HTTP | `tests/api/test_content.py`                                        | `TestContentFavorite.test_unfavorite_content` (`repo/tests/api/test_content.py:159`)                                      |
| POST /content/:content_id/download              | yes     | true no-mock HTTP | `tests/api/test_content.py`                                        | `TestContentDownload.test_download_content` (`repo/tests/api/test_content.py:177`)                                        |
| POST /content/:content_id/report                | yes     | true no-mock HTTP | `tests/api/test_content.py`                                        | `TestContentModeration.test_report_content` (`repo/tests/api/test_content.py:252`)                                        |
| POST /moderation/cases/:case_id/decision        | yes     | true no-mock HTTP | `tests/api/test_content.py`                                        | `TestContentModeration.test_moderation_suppress` (`repo/tests/api/test_content.py:272`)                                   |
| POST /moderation/cases/:case_id/appeal          | yes     | true no-mock HTTP | `tests/api/test_content.py`                                        | `TestContentModeration.test_appeal_and_approve` (`repo/tests/api/test_content.py:299`)                                    |
| POST /moderation/cases/:case_id/appeal-decision | yes     | true no-mock HTTP | `tests/api/test_content.py`                                        | `TestContentModeration.test_appeal_and_approve` (`repo/tests/api/test_content.py:299`)                                    |
| POST /resources                                 | yes     | true no-mock HTTP | `tests/api/test_booking.py`                                        | `TestResources.test_create_resource` (`repo/tests/api/test_booking.py:48`)                                                |
| GET /resources                                  | yes     | true no-mock HTTP | `tests/api/test_booking.py`                                        | `TestResources.test_list_resources` (`repo/tests/api/test_booking.py:59`)                                                 |
| POST /slot-templates                            | yes     | true no-mock HTTP | `tests/api/test_booking.py`                                        | `TestSlotTemplates.test_create_slot_template` (`repo/tests/api/test_booking.py:73`)                                       |
| GET /availability                               | yes     | true no-mock HTTP | `tests/api/test_booking.py`                                        | `TestAvailability.test_get_availability` (`repo/tests/api/test_booking.py:95`)                                            |
| POST /reservations/hold                         | yes     | true no-mock HTTP | `tests/api/test_booking.py`                                        | `TestReservations.test_hold_reservation` (`repo/tests/api/test_booking.py:109`)                                           |
| POST /reservations/:reservation_id/confirm      | yes     | true no-mock HTTP | `tests/api/test_booking.py`                                        | `TestReservations.test_confirm_reservation` (`repo/tests/api/test_booking.py:126`)                                        |
| POST /reservations/:reservation_id/cancel       | yes     | true no-mock HTTP | `tests/api/test_booking.py`                                        | `TestReservations.test_cancel_held_reservation` (`repo/tests/api/test_booking.py:151`)                                    |
| POST /reservations/:reservation_id/reschedule   | yes     | true no-mock HTTP | `tests/api/test_booking.py`                                        | `TestReservations.test_reschedule_reservation` (`repo/tests/api/test_booking.py:210`)                                     |
| GET /reservations                               | yes     | true no-mock HTTP | `tests/api/test_booking.py`                                        | `TestListReservations.test_list_reservations` (`repo/tests/api/test_booking.py:331`)                                      |
| GET /admin/system-status                        | yes     | true no-mock HTTP | `tests/api/test_admin.py`                                          | `TestSystemStatus.test_system_status_success` (`repo/tests/api/test_admin.py:23`)                                         |
| GET /admin/debug/routes                         | yes     | true no-mock HTTP | `tests/api/test_admin.py`                                          | `TestDebugEndpoints.test_debug_routes_disabled` (`repo/tests/api/test_admin.py:32`)                                       |
| GET /admin/debug/config-redacted                | yes     | true no-mock HTTP | `tests/api/test_admin.py`                                          | `TestDebugEndpoints.test_config_redacted` (`repo/tests/api/test_admin.py:40`)                                             |
| GET /health                                     | yes     | true no-mock HTTP | `tests/api/test_admin.py`, `tests/api/test_security.py`            | `TestHealthEndpoint.test_health_endpoint` (`repo/tests/api/test_admin.py:8`)                                              |

## API Test Classification

- Total API test functions in `tests/api`: `124` (`rg -n "def test_" repo/tests/api`).
- Classification:
  - True No-Mock HTTP: `122` (all endpoint-mapping tests use Flask `test_client` against `create_app` routes with no test-level mocking in `tests/api`).
  - HTTP with Mocking: `0` (no `patch`, `MagicMock`, `monkeypatch`, `jest.mock`, `vi.mock`, `sinon.stub` found in `tests/api`).
  - Non-HTTP (unit/invariant tests placed under API folder): `2`.
    - `test_password_hash_column_is_encrypted` (`repo/tests/api/test_prompt_compliance.py:808`)
    - `test_token_hash_uses_keyed_hmac` (`repo/tests/api/test_prompt_compliance.py:814`)

## Mock Detection

- API tests (`tests/api`): no mock/stub patterns detected by static scan.
- Unit tests (`tests/unit`) do use mocking:
  - `repo/tests/unit/test_pagination.py:4,13,15,17` (`MagicMock` query-chain stubs for pagination utility).
  - `repo/tests/unit/test_auth_middleware.py:4` (`patch`, `MagicMock` imported; static presence of mocking dependency).
  - `repo/tests/unit/test_middleware_controls.py:12` (`MagicMock`, `patch` imported).
  - `repo/tests/unit/test_scheduler.py:6` (`patch` imported).

## Coverage Summary

- Total endpoints: `55`.
- Endpoints with HTTP tests: `55`.
- Endpoints with TRUE no-mock HTTP tests: `55`.
- HTTP coverage: `100%`.
- True API coverage: `100%`.

## Unit Test Summary

### Backend Unit Tests

- Test files: `tests/unit/*.py` (19 files found).
- Controllers/API modules covered (via HTTP tests in `tests/api`): auth, permissions, invitations, booking, content/moderation, analytics/exports, audit/alerts, admin/debug, health.
- Services covered:
  - No concrete service-layer modules beyond package stubs (`src/services/__init__.py` only).
- Repositories covered:
  - No concrete repository modules beyond package stubs (`src/repositories/__init__.py` only).
- Auth/guards/middleware covered:
  - `src/security/auth_middleware.py` (`tests/unit/test_auth_middleware.py`)
  - signing/rate-limit/TLS controls (`tests/unit/test_middleware_controls.py`)
  - middleware behavior via HTTP (`tests/api/test_middleware_integration.py`)
- Important backend modules not directly unit-tested:
  - `src/logging/__init__.py` (no dedicated tests observed).
  - `migrations/*` and migration flow logic (no tests observed).

### Frontend Unit Tests (STRICT)

- Frontend test files: `NONE`.
- Frameworks/tools detected for frontend tests: `NONE`.
- Frontend components/modules covered: `NONE`.
- Important frontend components/modules not tested: `N/A` (no frontend codebase detected).
- Mandatory verdict: **Frontend unit tests: MISSING**.
- CRITICAL GAP rule: `NOT TRIGGERED` because project type is `backend`, not `fullstack`/`web`.

### Cross-Layer Observation

- Not applicable: no frontend layer detected.

## API Observability Check

- Strong observability in many tests: explicit method/path + payload/query + response/body assertions.
  - Examples: `repo/tests/api/test_booking.py:109,126,210`, `repo/tests/api/test_content.py:195,252,299`, `repo/tests/api/test_analytics.py:10,38,85,138,196`.
- Weak spots (request/response validation shallow):
  - Some tests assert status only or minimal body checks (e.g., `repo/tests/api/test_invitations.py:52`, `repo/tests/api/test_invitations.py:69`, `repo/tests/api/test_booking.py:432`).

## Tests Check

- Success paths: broadly covered across all endpoint groups.
- Failure paths: covered (401/403/409/410/423 etc.) across auth/security/booking/content/invitations.
- Edge cases: partially strong (idempotency replay, overlap conflicts, version conflict, blacklist cooldown, recommendations filters).
- Validation coverage: present but uneven per endpoint (some endpoints rely on status-only assertions).
- Auth/permissions coverage: strong (role checks, token flows, cross-org isolation, context switching).
- Integration boundaries: moderate; tests often interact with DB directly for setup, reducing strict black-box behavior for some scenarios.
- `run_tests.sh` check:
  - Docker-based execution: yes (`docker compose run ... pytest`) (`repo/run_tests.sh`).
  - Local dependency requirement beyond Docker runtime installs: not present.

## End-to-End Expectations

- Project type is backend; full FE↔BE E2E expectation does not apply.

## Test Coverage Score (0-100)

- **Score: 90/100**

## Score Rationale

- - Excellent endpoint-level HTTP coverage (55/55).
- - True no-mock HTTP endpoint tests are present.
- - Strong security/business-rule scenarios included.
- - Some tests are not fully black-box (manual DB state mutation for setup/forcing states).
- - Several assertions are shallow (status-only/minimal payload checks).
- - API folder mixes non-HTTP invariant tests, reducing organizational clarity.

## Key Gaps

1. Variable assertion depth: multiple tests validate status but not response contract details.
2. Mixed testing styles in `tests/api` (HTTP + non-HTTP invariant tests) complicate auditability.
3. No explicit migration-test coverage for schema migration safety.

## Confidence and Assumptions

- Confidence: high for static endpoint/test mapping; medium for runtime behavioral sufficiency because tests were not executed.
- Assumptions:
  - Flask route decorators in `src/api/*` are the authoritative endpoint source.
  - `create_app(testing=True)` + `app.test_client()` implies real route-handler execution path for endpoint tests.

## Test Coverage Verdict

- **PASS WITH GAPS** (high coverage; quality depth inconsistencies remain).

---

# README Audit

## README Location Check

- Required file exists: `repo/README.md`.

## Hard Gate Evaluation

### Formatting

- PASS: Markdown is structured and readable with clear sections and tables.

### Startup Instructions (Backend/Fullstack)

- PASS: includes `docker-compose up --build` (`repo/README.md`, Quick Start / Run Commands).

### Access Method

- PASS: explicitly states URL and port (`http://localhost:5000`).

### Verification Method

- PASS: includes concrete verification flow with `curl` (health, login, protected endpoint).

### Environment Rules (Docker-contained)

- PASS: explicitly states Docker-only setup and no host-level runtime install requirement.
- Note: optional host cert scripts are provided, but Dockerized certificate generation alternative is also documented.

### Demo Credentials (Auth Conditional)

- PASS: auth exists and credentials for all roles are documented (platform admin, org admin, member, guest).

## Engineering Quality

- Tech stack clarity: strong (Flask, SQLite, security controls, scheduler, TLS notes).
- Architecture explanation: moderate-to-strong via route inventory and security model sections.
- Testing instructions: strong (`./run_tests.sh`, Docker-based).
- Security/roles documentation: strong.
- Workflow clarity: strong for local run + verification.
- Presentation quality: good overall; minor encoding artifacts visible in some dashes.

## High Priority Issues

- None.

## Medium Priority Issues

1. README claims complete Docker-only posture but also includes optional host script paths for TLS cert generation; this can create policy ambiguity for strict reviewers.

## Low Priority Issues

1. Minor character encoding artifacts (mojibake) reduce polish/readability in a few lines.

## Hard Gate Failures

- None.

## README Verdict

- **PASS**

---

## Final Combined Verdicts

- Test Coverage Audit: **PASS WITH GAPS**
- README Audit: **PASS**
