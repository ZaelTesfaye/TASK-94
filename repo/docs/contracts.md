# API Contract Specification

All endpoints return JSON. Successful responses use `{"data": ...}`, list endpoints use `{"data": [...], "pagination": {...}}`, errors use `{"error": {"code": "...", "message": "..."}, "meta": {"request_id": "...", "timestamp": "..."}}`.

Authentication is via `Authorization: Bearer <access_token>` header unless noted as public.

## Auth (`/auth`)

| Method | Path | Auth | Role | Description |
|---|---|---|---|---|
| POST | `/auth/register-guest` | No | -- | Register a guest account |
| POST | `/auth/login` | No | -- | Login with credentials |
| POST | `/auth/refresh` | No | -- | Refresh token pair (rotation) |
| POST | `/auth/logout` | Yes | Any | Logout current session |
| POST | `/auth/logout-all` | Yes | Any | Revoke all sessions |
| POST | `/auth/device/bind` | Yes | Any | Bind device fingerprint |
| POST | `/auth/device/unbind` | Yes | Any | Unbind a device |

### POST `/auth/register-guest`
- Request: `{"username": str, "password": str, "display_name": str?}`
- Response (201): `{"user": {...}, "access_token": str, "refresh_token": str}`

### POST `/auth/login`
- Request: `{"username": str, "password": str, "device_fingerprint": str?, "captcha_id": str?, "captcha_answer": str?}`
- Response (200): `{"access_token": str, "refresh_token": str, "expires_in": int, "user": {...}}`
- Error (423): Account locked -- `{"retry_after": int}`
- Error (403): CAPTCHA required -- returns challenge payload

### POST `/auth/refresh`
- Request: `{"refresh_token": str}`
- Response (200): `{"access_token": str, "refresh_token": str, "expires_in": int}`

## Permissions (`/permissions`)

| Method | Path | Auth | Role | Description |
|---|---|---|---|---|
| GET | `/permissions` | Yes | Any | List permission definitions |
| POST | `/permissions` | Yes | Platform Admin | Create a permission |
| POST | `/permissions/assign` | Yes | Org Admin+ | Assign permission to user |
| POST | `/permissions/revoke` | Yes | Org Admin+ | Revoke permission from user |
| GET | `/permissions/memberships` | Yes | Any | List caller's memberships |
| POST | `/permissions/memberships/switch-context` | Yes | Any | Switch org context |

### POST `/permissions/assign`
- Request: `{"user_id": uuid, "permission_code": str, "organization_id": uuid?}`
- Response (201): `{"id": uuid, "user_id": uuid, "permission_code": str, ...}`

## Invitations (`/invitations`)

| Method | Path | Auth | Role | Description |
|---|---|---|---|---|
| POST | `/invitations` | Yes | Org Admin+ | Create invitation code |
| GET | `/invitations` | Yes | Org Admin+ | List invitations |
| POST | `/invitations/redeem` | Yes | Any | Redeem an invitation code |
| POST | `/invitations/revoke` | Yes | Org Admin+ | Revoke a pending invitation |

### POST `/invitations`
- Request: `{"organization_id": uuid, "target_role": str, "email_hint": str?}`
- Response (201): `{"id": uuid, "code": str, "organization_id": uuid, "target_role": str, "status": "PENDING", "expires_at": iso8601}`

### POST `/invitations/redeem`
- Request: `{"code": str}`
- Response (200): `{"membership_id": uuid, "organization_id": uuid, "role": str}`

## Booking

| Method | Path | Auth | Role | Description |
|---|---|---|---|---|
| POST | `/resources` | Yes | Org Admin+ | Create a resource |
| GET | `/resources` | Yes | Member+ | List resources |
| POST | `/slot-templates` | Yes | Org Admin+ | Create slot template |
| GET | `/slot-templates` | Yes | Member+ | List slot templates |
| POST | `/reservations/hold` | Yes | Member+ | Place a hold |
| POST | `/reservations/<id>/confirm` | Yes | Member+ | Confirm a held reservation |
| POST | `/reservations/<id>/cancel` | Yes | Member+ | Cancel a reservation |
| POST | `/reservations/<id>/reschedule` | Yes | Member+ | Reschedule a confirmed reservation |
| GET | `/reservations` | Yes | Member+ | List reservations |

### POST `/reservations/hold`
- Request: `{"resource_id": uuid, "start_time": iso8601, "end_time": iso8601, "idempotency_key": str?, "notes": str?}`
- Response (201): `{"id": uuid, "status": "HELD", "hold_expires_at": iso8601, ...}`
- Error (409): Overlapping reservation exists

## Content

| Method | Path | Auth | Role | Description |
|---|---|---|---|---|
| POST | `/content` | Yes | Member+ | Create content item |
| GET | `/content` | Yes | Member+ | List content items |
| GET | `/content/<id>` | Yes | Member+ | Get content detail |
| POST | `/content/<id>/rate` | Yes | Member+ | Rate content (1-5) |
| POST | `/content/<id>/comment` | Yes | Member+ | Add comment |
| POST | `/content/<id>/favorite` | Yes | Member+ | Toggle favorite |
| POST | `/content/<id>/download` | Yes | Member+ | Record download |
| POST | `/content/<id>/report` | Yes | Member+ | Report content |
| POST | `/moderation/<id>/review` | Yes | Org Admin+ | Review moderation case |
| POST | `/moderation/<id>/appeal` | Yes | Member+ | Appeal a suppression |

## Analytics

| Method | Path | Auth | Role | Description |
|---|---|---|---|---|
| POST | `/learning-events` | Yes | Member+ | Ingest learning event |
| GET | `/analytics/completion` | Yes | Org Admin+ | Completion statistics |
| GET | `/analytics/behavior` | Yes | Org Admin+ | Behavior analytics |
| GET | `/analytics/difficulty` | Yes | Org Admin+ | Question difficulty stats |
| POST | `/exports` | Yes | Org Admin+ | Request a CSV export |
| GET | `/exports` | Yes | Org Admin+ | List exports |
| GET | `/exports/<id>/download` | Yes | Org Admin+ | Download export file |

## Audit (`/audit-events`, `/alerts`)

| Method | Path | Auth | Role | Description |
|---|---|---|---|---|
| GET | `/audit-events` | Yes | Org Admin+ | List audit events (immutable) |
| GET | `/alerts` | Yes | Org Admin+ | List alerts |
| POST | `/alerts/<id>/ack` | Yes | Org Admin+ | Acknowledge an alert |
| POST | `/alerts/<id>/resolve` | Yes | Org Admin+ | Resolve an alert |

## Admin (`/admin`)

| Method | Path | Auth | Role | Description |
|---|---|---|---|---|
| GET | `/admin/system-status` | Yes | Platform Admin | System statistics |
| GET | `/admin/debug/routes` | Yes | Platform Admin | List all routes (debug only) |
| GET | `/admin/debug/config-redacted` | Yes | Platform Admin | Redacted config dump (debug only) |

## Health (public)

| Method | Path | Auth | Description |
|---|---|---|---|
| GET | `/health` | No | Database connectivity and service status |

### Response shape
- Success: `{"data": {"status": "healthy", "database": "connected", "timestamp": "...", "version": "..."}}`
- Failure (503): `{"error": {"code": "UNHEALTHY", "message": "..."}, ...}`
