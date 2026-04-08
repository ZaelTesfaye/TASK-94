# Data Model

All tables defined in `src/models/models.py`. Primary keys are UUID v4 strings (36 chars). Timestamps use UTC with timezone.

## Core Tables

### users

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | String(36) | PK, default uuid4 | |
| username | String(255) | Unique, Not Null, Indexed | |
| password_hash | Text | Not Null | bcrypt hash |
| display_name | String(255) | Nullable | |
| email | String(255) | Nullable | |
| role | String(50) | Not Null, default "guest" | RoleType enum value |
| status | String(50) | Not Null, default "ACTIVE" | UserStatus enum (ACTIVE/INACTIVE/SUSPENDED) |
| is_active | Boolean | Not Null, default True | |
| last_login_at | DateTime(tz) | Nullable | Updated on each successful login |
| created_at | DateTime(tz) | Not Null | |
| updated_at | DateTime(tz) | Not Null, auto-update | |

Relationships: `memberships`, `devices`, `reservations`

### organizations

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | String(36) | PK | |
| name | String(255) | Not Null | |
| slug | String(255) | Unique, Not Null, Indexed | URL-safe identifier |
| is_active | Boolean | Not Null, default True | |
| created_at | DateTime(tz) | Not Null | |
| updated_at | DateTime(tz) | Not Null, auto-update | |

Relationships: `memberships`, `resources`

### memberships

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | String(36) | PK | |
| user_id | String(36) | FK(users.id), Not Null, Indexed | |
| organization_id | String(36) | FK(organizations.id), Not Null, Indexed | |
| role | String(50) | Not Null, default "member" | Role within the org |
| is_active | Boolean | Not Null, default True | |
| created_at | DateTime(tz) | Not Null | |

Unique constraint: `(user_id, organization_id)`

### permissions

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | String(36) | PK | |
| code | String(255) | Unique, Not Null, Indexed | e.g. "content.create" |
| description | Text | Nullable | |
| data_scope | String(50) | Nullable | organization / site / resource |
| created_at | DateTime(tz) | Not Null | |

### user_permissions

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | String(36) | PK | |
| user_id | String(36) | FK(users.id), Not Null, Indexed | |
| permission_id | String(36) | FK(permissions.id), Not Null, Indexed | |
| organization_id | String(36) | FK(organizations.id), Nullable, Indexed | Null = global |
| granted_by | String(36) | FK(users.id), Nullable | |
| created_at | DateTime(tz) | Not Null | |

Unique constraint: `(user_id, permission_id, organization_id)`

## Booking Tables

### resources

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | String(36) | PK | |
| organization_id | String(36) | FK(organizations.id), Not Null, Indexed | |
| name | String(255) | Not Null | |
| description | Text | Nullable | |
| resource_type | String(100) | Nullable | |
| capacity | Integer | Not Null, default 1 | Fallback quota |
| is_active | Boolean | Not Null, default True | |
| created_at / updated_at | DateTime(tz) | Not Null | |

### slot_templates

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | String(36) | PK | |
| resource_id | String(36) | FK(resources.id), Not Null, Indexed | |
| day_of_week | Integer | Not Null | 0=Mon, 6=Sun |
| start_time | Time | Not Null | |
| end_time | Time | Not Null | |
| quota | Integer | Not Null, default 1 | Max concurrent bookings |
| is_active | Boolean | Not Null, default True | |
| created_at | DateTime(tz) | Not Null | |

### reservations

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | String(36) | PK | |
| user_id | String(36) | FK(users.id), Not Null, Indexed | |
| resource_id | String(36) | FK(resources.id), Not Null, Indexed | |
| organization_id | String(36) | FK(organizations.id), Not Null, Indexed | |
| status | String(50) | Not Null, default "HELD" | ReservationStatus enum |
| start_time | DateTime(tz) | Not Null | |
| end_time | DateTime(tz) | Not Null | |
| hold_expires_at | DateTime(tz) | Nullable | Set on HELD |
| version | Integer | Not Null, default 1 | Optimistic concurrency |
| idempotency_key | String(255) | Nullable, Indexed | |
| notes | Text | Nullable | |
| created_at / updated_at | DateTime(tz) | Not Null | |

State transitions: HELD -> CONFIRMED / CANCELLED / RELEASED; CONFIRMED -> CANCELLED / RESCHEDULED; terminal: CANCELLED, RELEASED, RESCHEDULED.

## Content Tables

### content_items

| Column | Type | Constraints | Notes |
|---|---|---|---|
| id | String(36) | PK | |
| organization_id | String(36) | FK, Not Null, Indexed | |
| creator_id | String(36) | FK(users.id), Not Null, Indexed | |
| title | String(500) | Not Null | |
| body | Text | Nullable | |
| content_type | String(50) | Not Null, default "ARTICLE" | ContentType enum |
| quality_state | String(50) | Not Null, default "ACTIVE" | ContentQualityState enum |
| fingerprint_hash | String(64) | Nullable, Indexed | SHA-256 of normalized title+body |
| avg_rating | Float | Not Null, default 0.0 | |
| rating_count | Integer | Not Null, default 0 | |
| view_count / download_count | Integer | Not Null, default 0 | |
| is_active | Boolean | Not Null, default True | |
| created_at / updated_at | DateTime(tz) | Not Null | |

### content_ratings -- Unique: `(user_id, content_id)`, score 1-5
### content_comments -- user_id, content_id, body, is_visible
### content_favorites -- Unique: `(user_id, content_id)`
### content_downloads -- user_id, content_id, created_at
### moderation_cases -- content_id, reporter_id, reviewer_id, action, reason, encrypted decision/appeal notes

## Analytics Tables

### learning_events -- user_id, organization_id, content_id, event_type (LearningEventType), metadata_json
### questions -- content_id, organization_id, question_text, correct_answer, options_json, difficulty_bucket, total_attempts, correct_attempts
### attempts -- user_id, question_id, organization_id, answer_given, is_correct
### exports -- requester_id, organization_id, export_type, parameters_json, parameters_hash, status, file_path
### user_cohorts -- Unique: `(user_id, cohort_tag, organization_id)`

## Support Tables

### refresh_tokens -- user_id, token_hash (AES-256-GCM encrypted HMAC hash), token_lookup_hash (HMAC-SHA256 deterministic, unique, indexed), device_id, is_revoked, expires_at
### access_token_denylist -- jti (unique), expires_at
### invitation_codes -- code (unique), issuer_id, organization_id, target_role, status, redeemed_by_id, expires_at
### devices -- user_id, fingerprint_hash (AES-256-GCM), fingerprint_lookup_hash (HMAC-SHA256, indexed), risk_score, status
### idempotency_records -- Unique: `(user_id, endpoint, key_hash)`, response_code, response_body, expires_at
### nonce_store -- nonce (unique), expires_at
### rate_limit_buckets -- bucket_key (indexed), tokens, last_refill_at
### login_challenges -- user_id, ip_address, challenge_type, challenge_data, expected_answer, is_solved, expires_at
### login_failure_counters -- identifier (unique), failure_count, first_failure_at, locked_until
### audit_events -- event_type, actor_id, actor_ip, target_type, target_id, organization_id, before_state, after_state, metadata_json (insert-only)
### alerts -- alert_type, severity, status (OPEN/ACKNOWLEDGED/RESOLVED), title, description, organization_id, acknowledged_by/at, resolved_by/at
