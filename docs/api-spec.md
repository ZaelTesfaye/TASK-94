# API Specification

Complete API specification with request/response examples for the Learning & Resource Booking Governance API.

---

## Table of Contents

1. [Base URL & Conventions](#base-url--conventions)
2. [Authentication Model](#authentication-model)
3. [Response Envelopes](#response-envelopes)
4. [Error Codes](#error-codes)
5. [Health Check](#health-check)
6. [Authentication Endpoints](#authentication-endpoints)
7. [Permission Management](#permission-management)
8. [Invitation System](#invitation-system)
9. [Resource Booking](#resource-booking)
10. [Content Management](#content-management)
11. [Moderation](#moderation)
12. [Analytics](#analytics)
13. [Audit & Alerts](#audit--alerts)
14. [Admin Endpoints](#admin-endpoints)

---

## Base URL & Conventions

**Base URL**: `http://localhost:5000` (default Docker deployment)

### HTTP Methods

- `GET` - Retrieve resources (idempotent, no side effects)
- `POST` - Create resources or trigger actions
- `PATCH` - Partial update (not currently used)
- `DELETE` - Remove resources
- `PUT` - Replace resource (not currently used)

### Common Headers

**Request Headers**:

```
Authorization: Bearer <access_token>    # Required for protected endpoints
Content-Type: application/json          # Required for POST/PATCH/PUT
Idempotency-Key: <unique-string>        # Required for state-changing booking operations
X-Timestamp: 2026-04-08T10:30:00Z       # Optional for request signing
X-Nonce: <unique-nonce>                 # Optional for request signing
X-Signature: <hmac-sha256-hex>          # Optional for request signing
```

**Response Headers**:

```
Content-Type: application/json
X-RateLimit-Limit: 60                   # Requests allowed per minute
X-RateLimit-Remaining: 45               # Requests remaining in current window
X-RateLimit-Reset: 1712575800           # Unix timestamp when limit resets
```

---

## Authentication Model

### Role Hierarchy

| Role             | Scope        | Permissions                                           |
| ---------------- | ------------ | ----------------------------------------------------- |
| `platform_admin` | Global       | Full system access, admin endpoints, debug endpoints  |
| `org_admin`      | Organization | Manage org resources, users, invitations, permissions |
| `member`         | Organization | Access org resources, create content, book resources  |
| `guest`          | None         | Self-service registration, limited access             |

### Permission Codes

Fine-grained permissions beyond roles:

- `moderation:review` - Review and decide on moderation cases
- `moderation:appeal` - Review appeals against moderation decisions
- `analytics:view` - Access analytics endpoints
- `export:create` - Create data exports
- `audit:view` - View audit logs

### Token Lifecycle

1. **Registration/Login** → Receive `access_token` (30min) + `refresh_token` (14 days)
2. **API Requests** → Include `Authorization: Bearer <access_token>` header
3. **Token Expiry** → Call `/auth/refresh` with `refresh_token` to get new token pair
4. **Logout** → Call `/auth/logout` to revoke tokens

---

## Response Envelopes

### Success Response (Single Resource)

```json
{
  "data": {
    "id": "abc-123",
    "name": "Resource Name",
    "created_at": "2026-04-08T10:30:00Z"
  },
  "meta": {
    "request_id": "550e8400-e29b-41d4-a716-446655440000",
    "timestamp": "2026-04-08T10:30:15Z"
  }
}
```

### Success Response (List/Paginated)

```json
{
  "data": [
    { "id": "1", "name": "Item 1" },
    { "id": "2", "name": "Item 2" }
  ],
  "meta": {
    "request_id": "550e8400-e29b-41d4-a716-446655440000",
    "timestamp": "2026-04-08T10:30:15Z"
  },
  "pagination": {
    "page": 1,
    "per_page": 20,
    "total": 45,
    "total_pages": 3,
    "has_next": true,
    "has_prev": false
  }
}
```

### Error Response

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Username is required",
    "details": null
  },
  "meta": {
    "request_id": "550e8400-e29b-41d4-a716-446655440000",
    "timestamp": "2026-04-08T10:30:15Z"
  }
}
```

---

## Error Codes

### HTTP Status Codes

| Code | Meaning               | When Used                                                                      |
| ---- | --------------------- | ------------------------------------------------------------------------------ |
| 200  | OK                    | Successful GET, POST (non-creation), PATCH                                     |
| 201  | Created               | Resource successfully created                                                  |
| 204  | No Content            | Successful DELETE or action with no return value                               |
| 400  | Bad Request           | Validation error, missing required fields                                      |
| 401  | Unauthorized          | Missing, invalid, or expired access token                                      |
| 403  | Forbidden             | Valid token but insufficient permissions, captcha required, device blacklisted |
| 404  | Not Found             | Resource does not exist                                                        |
| 409  | Conflict              | Duplicate resource, version conflict, slot unavailable                         |
| 410  | Gone                  | Resource expired (hold, invitation)                                            |
| 422  | Unprocessable Entity  | Semantic validation error                                                      |
| 423  | Locked                | Account locked due to failed login attempts                                    |
| 429  | Too Many Requests     | Rate limit exceeded                                                            |
| 500  | Internal Server Error | Unexpected server error                                                        |
| 503  | Service Unavailable   | Health check failure, database down                                            |

### Application Error Codes

| Code                  | HTTP Status | Description                           |
| --------------------- | ----------- | ------------------------------------- |
| `VALIDATION_ERROR`    | 400         | Input validation failed               |
| `INVALID_CREDENTIALS` | 401         | Username or password incorrect        |
| `TOKEN_EXPIRED`       | 401         | Access token has expired              |
| `INVALID_TOKEN`       | 401         | Malformed or tampered token           |
| `FORBIDDEN`           | 403         | User lacks required permission        |
| `CAPTCHA_REQUIRED`    | 403         | Must solve captcha before proceeding  |
| `DEVICE_BLACKLISTED`  | 403         | Device fingerprint is blacklisted     |
| `NOT_FOUND`           | 404         | Requested resource does not exist     |
| `USERNAME_TAKEN`      | 409         | Username already registered           |
| `SLOT_UNAVAILABLE`    | 409         | Booking slot is full or overlaps      |
| `VERSION_CONFLICT`    | 409         | Optimistic locking version mismatch   |
| `ALREADY_REDEEMED`    | 409         | Invitation already used               |
| `HOLD_EXPIRED`        | 410         | Reservation hold has expired          |
| `INVITATION_EXPIRED`  | 410         | Invitation is past expiry date        |
| `LOCKED_OUT`          | 423         | Account locked due to failed attempts |
| `RATE_LIMITED`        | 429         | Too many requests                     |

---

## Health Check

### GET /health

Check system health status.

**Auth**: None (public)

**Request**:

```http
GET /health HTTP/1.1
Host: localhost:5000
```

**Response 200 (Healthy)**:

```json
{
  "data": {
    "status": "healthy",
    "database": "connected",
    "scheduler": "running",
    "timestamp": "2026-04-08T10:30:00Z"
  },
  "meta": {
    "request_id": "550e8400-e29b-41d4-a716-446655440000",
    "timestamp": "2026-04-08T10:30:00Z"
  }
}
```

**Response 503 (Unhealthy)**:

```json
{
  "data": {
    "status": "unhealthy",
    "database": "disconnected",
    "scheduler": "stopped",
    "timestamp": "2026-04-08T10:30:00Z"
  },
  "meta": {
    "request_id": "550e8400-e29b-41d4-a716-446655440000",
    "timestamp": "2026-04-08T10:30:00Z"
  }
}
```

---

## Authentication Endpoints

### POST /auth/register-guest

Register a new guest user account.

**Auth**: None (public)

**Request**:

```http
POST /auth/register-guest HTTP/1.1
Host: localhost:5000
Content-Type: application/json

{
  "username": "alice",
  "password": "SecurePass123!",
  "display_name": "Alice Cooper"
}
```

**Request Body Fields**:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `username` | string | Yes | Unique username (alphanumeric, 3-50 chars) |
| `password` | string | Yes | Password (min 8 chars) |
| `display_name` | string | No | Human-readable name |

**Response 201**:

```json
{
  "data": {
    "user": {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "username": "alice",
      "display_name": "Alice Cooper",
      "role": "guest",
      "created_at": "2026-04-08T10:30:00Z"
    },
    "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
    "refresh_token": "refresh_abc123def456...",
    "expires_in": 1800
  },
  "meta": {
    "request_id": "550e8400-e29b-41d4-a716-446655440000",
    "timestamp": "2026-04-08T10:30:00Z"
  }
}
```

**Error Responses**:

- `400 VALIDATION_ERROR` - Missing username or password
- `409 USERNAME_TAKEN` - Username already exists

---

### POST /auth/login

Authenticate an existing user.

**Auth**: None (public)

**Request**:

```http
POST /auth/login HTTP/1.1
Host: localhost:5000
Content-Type: application/json

{
  "username": "alice",
  "password": "SecurePass123!",
  "device_fingerprint": "fp_abc123...",
  "captcha_id": "cap_xyz789",
  "captcha_answer": "42"
}
```

**Request Body Fields**:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `username` | string | Yes | Username |
| `password` | string | Yes | Password |
| `device_fingerprint` | string | No | Browser fingerprint for device tracking |
| `captcha_id` | string | No* | Captcha challenge ID (*required if captcha triggered) |
| `captcha_answer` | string | No* | Captcha answer (*required if captcha triggered) |

**Response 200**:

```json
{
  "data": {
    "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
    "refresh_token": "refresh_abc123def456...",
    "expires_in": 1800,
    "user": {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "username": "alice",
      "role": "guest",
      "display_name": "Alice Cooper"
    }
  },
  "meta": {
    "request_id": "550e8400-e29b-41d4-a716-446655440000",
    "timestamp": "2026-04-08T10:30:00Z"
  }
}
```

**Error Responses**:

- `401 INVALID_CREDENTIALS` - Incorrect username or password
- `403 CAPTCHA_REQUIRED` - Captcha must be solved (response includes `captcha_challenge`)
  ```json
  {
    "error": {
      "code": "CAPTCHA_REQUIRED",
      "message": "Captcha challenge required",
      "details": {
        "captcha_id": "cap_xyz789",
        "question": "What is 5 + 7?"
      }
    },
    "meta": {...}
  }
  ```
- `403 DEVICE_BLACKLISTED` - Device fingerprint is blacklisted
- `423 LOCKED_OUT` - Account locked for 15 minutes after 5 failed attempts

---

### POST /auth/refresh

Exchange a refresh token for a new access token.

**Auth**: None (public, but requires valid refresh token)

**Request**:

```http
POST /auth/refresh HTTP/1.1
Host: localhost:5000
Content-Type: application/json

{
  "refresh_token": "refresh_abc123def456..."
}
```

**Response 200**:

```json
{
  "data": {
    "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
    "refresh_token": "refresh_new789xyz012..."
  },
  "meta": {
    "request_id": "550e8400-e29b-41d4-a716-446655440000",
    "timestamp": "2026-04-08T10:30:00Z"
  }
}
```

**Notes**:

- Old refresh token is invalidated (token rotation)
- New refresh token has full 14-day expiry from refresh time

**Error Responses**:

- `401 INVALID_TOKEN` - Refresh token is invalid, revoked, or expired

---

### POST /auth/logout

Revoke the current refresh token.

**Auth**: Required

**Request**:

```http
POST /auth/logout HTTP/1.1
Host: localhost:5000
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...
Content-Type: application/json

{
  "refresh_token": "refresh_abc123def456..."
}
```

**Request Body Fields**:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `refresh_token` | string | No | If provided, revoke this specific token; otherwise revoke current session |

**Response 204**:

```http
HTTP/1.1 204 No Content
```

**Error Responses**:

- `401 UNAUTHORIZED` - Invalid or missing access token

---

### POST /auth/logout-all

Revoke all refresh tokens for the user (across all devices).

**Auth**: Required

**Request**:

```http
POST /auth/logout-all HTTP/1.1
Host: localhost:5000
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...
```

**Response 204**:

```http
HTTP/1.1 204 No Content
```

---

### GET /auth/me

Get the authenticated user's profile.

**Auth**: Required

**Request**:

```http
GET /auth/me HTTP/1.1
Host: localhost:5000
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...
```

**Response 200**:

```json
{
  "data": {
    "user": {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "username": "alice",
      "display_name": "Alice Cooper",
      "email": null,
      "role": "guest",
      "is_active": true,
      "created_at": "2026-04-08T10:30:00Z"
    },
    "memberships": [
      {
        "id": "mem-001",
        "organization_id": "org-001",
        "organization_name": "Acme Corp",
        "role": "member",
        "is_active": true
      }
    ],
    "device_count": 2
  },
  "meta": {
    "request_id": "550e8400-e29b-41d4-a716-446655440000",
    "timestamp": "2026-04-08T10:30:00Z"
  }
}
```

---

## Permission Management

### GET /permissions

List all available permission codes.

**Auth**: Required

**Query Parameters**:
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `page` | integer | 1 | Page number |
| `per_page` | integer | 20 | Items per page (max 100) |

**Request**:

```http
GET /permissions?page=1&per_page=20 HTTP/1.1
Host: localhost:5000
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...
```

**Response 200**:

```json
{
  "data": [
    {
      "id": "perm-001",
      "code": "moderation:review",
      "description": "Review and decide on moderation cases",
      "data_scope": "organization",
      "created_at": "2026-04-01T00:00:00Z"
    },
    {
      "id": "perm-002",
      "code": "analytics:view",
      "description": "Access analytics endpoints",
      "data_scope": "organization",
      "created_at": "2026-04-01T00:00:00Z"
    }
  ],
  "pagination": {
    "page": 1,
    "per_page": 20,
    "total": 2,
    "total_pages": 1,
    "has_next": false,
    "has_prev": false
  },
  "meta": {
    "request_id": "550e8400-e29b-41d4-a716-446655440000",
    "timestamp": "2026-04-08T10:30:00Z"
  }
}
```

---

### POST /permissions/assign

Assign a permission to a user (org_admin only).

**Auth**: Required (`org_admin` role)

**Request**:

```http
POST /permissions/assign HTTP/1.1
Host: localhost:5000
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...
Content-Type: application/json

{
  "user_id": "550e8400-e29b-41d4-a716-446655440000",
  "permission_code": "moderation:review",
  "organization_id": "org-001"
}
```

**Request Body Fields**:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `user_id` | string | Yes | Target user ID |
| `permission_code` | string | Yes | Permission code to assign |
| `organization_id` | string | No | Scope permission to organization (null = global) |

**Response 201**:

```json
{
  "data": {
    "id": "up-001",
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "permission_code": "moderation:review",
    "organization_id": "org-001",
    "granted_by": "admin-user-id",
    "created_at": "2026-04-08T10:30:00Z"
  },
  "meta": {
    "request_id": "550e8400-e29b-41d4-a716-446655440000",
    "timestamp": "2026-04-08T10:30:00Z"
  }
}
```

**Error Responses**:

- `403 FORBIDDEN` - Not an org_admin
- `404 NOT_FOUND` - User or permission does not exist

---

## Invitation System

### POST /invitations

Create an invitation code for an organization.

**Auth**: Required (`org_admin` role)

**Request**:

```http
POST /invitations HTTP/1.1
Host: localhost:5000
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...
Content-Type: application/json

{
  "organization_id": "org-001",
  "target_role": "member"
}
```

**Response 201**:

```json
{
  "data": {
    "invitation": {
      "id": "inv-001",
      "code": "INV-ABC123DEF456",
      "organization_id": "org-001",
      "target_role": "member",
      "status": "PENDING",
      "created_by": "admin-user-id",
      "expires_at": "2026-04-11T10:30:00Z",
      "created_at": "2026-04-08T10:30:00Z"
    }
  },
  "meta": {
    "request_id": "550e8400-e29b-41d4-a716-446655440000",
    "timestamp": "2026-04-08T10:30:00Z"
  }
}
```

---

### POST /invitations/redeem

Redeem an invitation code to join an organization.

**Auth**: Required

**Request**:

```http
POST /invitations/redeem HTTP/1.1
Host: localhost:5000
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...
Content-Type: application/json

{
  "code": "INV-ABC123DEF456"
}
```

**Response 200**:

```json
{
  "data": {
    "membership": {
      "id": "mem-002",
      "user_id": "550e8400-e29b-41d4-a716-446655440000",
      "organization_id": "org-001",
      "role": "member",
      "is_active": true,
      "created_at": "2026-04-08T10:30:00Z"
    }
  },
  "meta": {
    "request_id": "550e8400-e29b-41d4-a716-446655440000",
    "timestamp": "2026-04-08T10:30:00Z"
  }
}
```

**Error Responses**:

- `404 NOT_FOUND` - Invalid invitation code
- `409 ALREADY_REDEEMED` - Invitation already used
- `410 INVITATION_EXPIRED` - Invitation past expiry date (72 hours)

---

## Resource Booking

### GET /availability

Query available time slots for a resource.

**Auth**: Required

**Query Parameters**:
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `resource_id` | string | Yes | Resource ID to query |
| `date` | string | Yes | Date in YYYY-MM-DD format |

**Request**:

```http
GET /availability?resource_id=res-001&date=2026-04-10 HTTP/1.1
Host: localhost:5000
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...
```

**Response 200**:

```json
{
  "data": {
    "slots": [
      {
        "start_time": "2026-04-10T09:00:00Z",
        "end_time": "2026-04-10T10:00:00Z",
        "quota": 5,
        "booked_count": 2,
        "available_count": 3
      },
      {
        "start_time": "2026-04-10T10:00:00Z",
        "end_time": "2026-04-10T11:00:00Z",
        "quota": 5,
        "booked_count": 5,
        "available_count": 0
      }
    ]
  },
  "meta": {
    "request_id": "550e8400-e29b-41d4-a716-446655440000",
    "timestamp": "2026-04-08T10:30:00Z"
  }
}
```

---

### POST /reservations/hold

Place a hold on a time slot (two-phase booking, step 1).

**Auth**: Required

**Idempotency**: Required (`Idempotency-Key` header)

**Request**:

```http
POST /reservations/hold HTTP/1.1
Host: localhost:5000
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...
Idempotency-Key: unique-booking-key-123
Content-Type: application/json

{
  "resource_id": "res-001",
  "start_time": "2026-04-10T14:00:00Z",
  "end_time": "2026-04-10T15:00:00Z",
  "organization_id": "org-001",
  "notes": "Team meeting room"
}
```

**Request Body Fields**:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `resource_id` | string | Yes | Resource to book |
| `start_time` | string | Yes | ISO 8601 timestamp (UTC) |
| `end_time` | string | Yes | ISO 8601 timestamp (UTC) |
| `organization_id` | string | Yes | Organization context |
| `notes` | string | No | Optional notes for the reservation |

**Response 201**:

```json
{
  "data": {
    "id": "rsv-001",
    "resource_id": "res-001",
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "organization_id": "org-001",
    "start_time": "2026-04-10T14:00:00Z",
    "end_time": "2026-04-10T15:00:00Z",
    "status": "HELD",
    "version": 1,
    "expires_at": "2026-04-08T10:40:00Z",
    "notes": "Team meeting room",
    "created_at": "2026-04-08T10:30:00Z"
  },
  "meta": {
    "request_id": "550e8400-e29b-41d4-a716-446655440000",
    "timestamp": "2026-04-08T10:30:00Z"
  }
}
```

**Notes**:

- Hold expires in 10 minutes (configurable via `HOLD_EXPIRY_MINUTES`)
- User can have max 3 active holds (configurable via `MAX_ACTIVE_HOLDS_PER_USER`)

**Error Responses**:

- `409 SLOT_UNAVAILABLE` - Slot is full or overlaps with existing reservation
- `400 VALIDATION_ERROR` - start_time >= end_time, or time in the past

---

### POST /reservations/{id}/confirm

Confirm a held reservation (two-phase booking, step 2).

**Auth**: Required

**Idempotency**: Required (`Idempotency-Key` header)

**Request**:

```http
POST /reservations/rsv-001/confirm HTTP/1.1
Host: localhost:5000
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...
Idempotency-Key: confirm-booking-key-456
Content-Type: application/json

{
  "version": 1
}
```

**Request Body Fields**:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `version` | integer | Yes | Optimistic locking version (from hold response) |

**Response 200**:

```json
{
  "data": {
    "id": "rsv-001",
    "resource_id": "res-001",
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "organization_id": "org-001",
    "start_time": "2026-04-10T14:00:00Z",
    "end_time": "2026-04-10T15:00:00Z",
    "status": "CONFIRMED",
    "version": 2,
    "expires_at": null,
    "confirmed_at": "2026-04-08T10:32:00Z",
    "notes": "Team meeting room",
    "created_at": "2026-04-08T10:30:00Z",
    "updated_at": "2026-04-08T10:32:00Z"
  },
  "meta": {
    "request_id": "550e8400-e29b-41d4-a716-446655440000",
    "timestamp": "2026-04-08T10:32:00Z"
  }
}
```

**Error Responses**:

- `404 NOT_FOUND` - Reservation does not exist
- `409 VERSION_CONFLICT` - Version mismatch (concurrent modification)
- `410 HOLD_EXPIRED` - Hold TTL has elapsed (must create new hold)

---

### POST /reservations/{id}/cancel

Cancel a reservation.

**Auth**: Required (must be reservation owner or org_admin)

**Idempotency**: Required (`Idempotency-Key` header)

**Request**:

```http
POST /reservations/rsv-001/cancel HTTP/1.1
Host: localhost:5000
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...
Idempotency-Key: cancel-booking-key-789
Content-Type: application/json

{
  "version": 2
}
```

**Response 200**:

```json
{
  "data": {
    "id": "rsv-001",
    "status": "CANCELLED",
    "version": 3,
    "cancelled_at": "2026-04-08T11:00:00Z",
    "updated_at": "2026-04-08T11:00:00Z"
  },
  "meta": {
    "request_id": "550e8400-e29b-41d4-a716-446655440000",
    "timestamp": "2026-04-08T11:00:00Z"
  }
}
```

---

### GET /reservations

List reservations with filtering.

**Auth**: Required

**Query Parameters**:
| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `status` | string | - | Filter by status (HELD, CONFIRMED, CANCELLED, EXPIRED) |
| `resource_id` | string | - | Filter by resource |
| `start_date` | string | - | Filter reservations starting on/after this date |
| `end_date` | string | - | Filter reservations ending on/before this date |
| `sort_by` | string | `created_at` | Sort field |
| `sort_order` | string | `desc` | Sort order (asc/desc) |
| `page` | integer | 1 | Page number |
| `per_page` | integer | 20 | Items per page |

**Request**:

```http
GET /reservations?status=CONFIRMED&page=1&per_page=10 HTTP/1.1
Host: localhost:5000
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...
```

**Response 200**:

```json
{
  "data": [
    {
      "id": "rsv-001",
      "resource_id": "res-001",
      "resource_name": "Conference Room A",
      "user_id": "550e8400-e29b-41d4-a716-446655440000",
      "start_time": "2026-04-10T14:00:00Z",
      "end_time": "2026-04-10T15:00:00Z",
      "status": "CONFIRMED",
      "notes": "Team meeting",
      "created_at": "2026-04-08T10:30:00Z"
    }
  ],
  "pagination": {
    "page": 1,
    "per_page": 10,
    "total": 1,
    "total_pages": 1,
    "has_next": false,
    "has_prev": false
  },
  "meta": {
    "request_id": "550e8400-e29b-41d4-a716-446655440000",
    "timestamp": "2026-04-08T10:30:00Z"
  }
}
```

---

## Content Management

### POST /content

Create a new content item.

**Auth**: Required

**Request**:

```http
POST /content HTTP/1.1
Host: localhost:5000
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...
Content-Type: application/json

{
  "title": "Introduction to Python",
  "body": "Python is a high-level programming language...",
  "content_type": "ARTICLE",
  "organization_id": "org-001"
}
```

**Request Body Fields**:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `title` | string | Yes | Content title (max 500 chars) |
| `body` | text | No | Content body |
| `content_type` | string | No | ARTICLE, VIDEO, QUIZ, COURSE (default: ARTICLE) |
| `organization_id` | string | Yes | Organization context |

**Response 201**:

```json
{
  "data": {
    "id": "cnt-001",
    "title": "Introduction to Python",
    "body": "Python is a high-level programming language...",
    "content_type": "ARTICLE",
    "quality_state": "NORMAL",
    "creator_id": "550e8400-e29b-41d4-a716-446655440000",
    "organization_id": "org-001",
    "rating_average": null,
    "rating_count": 0,
    "download_count": 0,
    "view_count": 0,
    "created_at": "2026-04-08T10:30:00Z"
  },
  "meta": {
    "request_id": "550e8400-e29b-41d4-a716-446655440000",
    "timestamp": "2026-04-08T10:30:00Z"
  }
}
```

**Error Responses**:

- `409 DUPLICATE_CONTENT` - Content fingerprint matches existing content

---

### POST /content/{id}/ratings

Rate a content item (1-5 stars).

**Auth**: Required

**Request**:

```http
POST /content/cnt-001/ratings HTTP/1.1
Host: localhost:5000
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...
Content-Type: application/json

{
  "score": 5
}
```

**Request Body Fields**:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `score` | integer | Yes | Rating score (1-5) |

**Response 200**:

```json
{
  "data": {
    "id": "rating-001",
    "content_id": "cnt-001",
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "score": 5,
    "created_at": "2026-04-08T10:30:00Z",
    "updated_at": "2026-04-08T10:30:00Z"
  },
  "meta": {
    "request_id": "550e8400-e29b-41d4-a716-446655440000",
    "timestamp": "2026-04-08T10:30:00Z"
  }
}
```

**Notes**:

- Users can update their rating (upsert behavior)
- If rating_count >= 20 and average < 2.0, content is demoted to `DEMOTED` quality state

**Error Responses**:

- `400 VALIDATION_ERROR` - Score not in range 1-5
- `404 NOT_FOUND` - Content does not exist

---

### POST /content/{id}/report

Report content for moderation review.

**Auth**: Required

**Request**:

```http
POST /content/cnt-001/report HTTP/1.1
Host: localhost:5000
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...
Content-Type: application/json

{
  "reason": "Spam content with misleading information"
}
```

**Response 201**:

```json
{
  "data": {
    "id": "case-001",
    "content_id": "cnt-001",
    "reporter_id": "550e8400-e29b-41d4-a716-446655440000",
    "reason": "Spam content with misleading information",
    "status": "PENDING",
    "created_at": "2026-04-08T10:30:00Z"
  },
  "meta": {
    "request_id": "550e8400-e29b-41d4-a716-446655440000",
    "timestamp": "2026-04-08T10:30:00Z"
  }
}
```

---

## Moderation

### POST /moderation/cases/{id}/decision

Issue a moderation decision (requires `moderation:review` permission).

**Auth**: Required (`moderation:review` permission)

**Request**:

```http
POST /moderation/cases/case-001/decision HTTP/1.1
Host: localhost:5000
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...
Content-Type: application/json

{
  "action": "SUPPRESS",
  "decision_notes": "Content violates community guidelines - contains spam"
}
```

**Request Body Fields**:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `action` | string | Yes | SUPPRESS or REINSTATE |
| `decision_notes` | text | Yes | Justification for decision |

**Response 200**:

```json
{
  "data": {
    "id": "case-001",
    "content_id": "cnt-001",
    "status": "DECIDED",
    "action": "SUPPRESS",
    "decided_by": "mod-user-id",
    "decision_notes": "Content violates community guidelines - contains spam",
    "decided_at": "2026-04-08T11:00:00Z"
  },
  "meta": {
    "request_id": "550e8400-e29b-41d4-a716-446655440000",
    "timestamp": "2026-04-08T11:00:00Z"
  }
}
```

**Error Responses**:

- `403 FORBIDDEN` - User lacks `moderation:review` permission
- `404 NOT_FOUND` - Case does not exist

---

### POST /moderation/cases/{id}/appeal

Submit an appeal (content creator only).

**Auth**: Required (must be original content creator)

**Request**:

```http
POST /moderation/cases/case-001/appeal HTTP/1.1
Host: localhost:5000
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...
Content-Type: application/json

{
  "appeal_notes": "This content does not violate guidelines. It is educational material cited from reputable sources..."
}
```

**Request Body Fields**:
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `appeal_notes` | text | Yes | Justification for appeal (min 50 chars) |

**Response 200**:

```json
{
  "data": {
    "id": "case-001",
    "status": "APPEAL_PENDING",
    "appeal_notes": "This content does not violate guidelines...",
    "appealed_at": "2026-04-08T12:00:00Z"
  },
  "meta": {
    "request_id": "550e8400-e29b-41d4-a716-446655440000",
    "timestamp": "2026-04-08T12:00:00Z"
  }
}
```

**Error Responses**:

- `403 FORBIDDEN` - Not the content creator
- `400 VALIDATION_ERROR` - appeal_notes too short (min 50 chars)

---

## Analytics

### GET /analytics/learning-behavior

Query learning behavior event metrics.

**Auth**: Required

**Query Parameters**:
| Parameter | Type | Description |
|-----------|------|-------------|
| `start_date` | string | Start date (YYYY-MM-DD) |
| `end_date` | string | End date (YYYY-MM-DD) |
| `event_type` | string | Filter by event type (VIEW, COMPLETE, etc.) |
| `cohort_tag` | string | Filter by cohort |
| `user_id` | string | Filter by specific user |

**Request**:

```http
GET /analytics/learning-behavior?start_date=2026-04-01&end_date=2026-04-30 HTTP/1.1
Host: localhost:5000
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...
```

**Response 200**:

```json
{
  "data": {
    "events": [
      {
        "event_type": "COMPLETE",
        "content_id": "cnt-001",
        "user_id": "550e8400-e29b-41d4-a716-446655440000",
        "timestamp": "2026-04-10T14:30:00Z",
        "duration_seconds": 3600
      }
    ],
    "summary": {
      "total_events": 150,
      "unique_users": 45,
      "avg_duration_seconds": 2400
    }
  },
  "meta": {
    "request_id": "550e8400-e29b-41d4-a716-446655440000",
    "timestamp": "2026-04-08T10:30:00Z"
  }
}
```

---

## Audit & Alerts

### GET /audit-events

Query the audit log (org_admin only).

**Auth**: Required (`org_admin` role)

**Query Parameters**:
| Parameter | Type | Description |
|-----------|------|-------------|
| `event_type` | string | Filter by event type |
| `actor_id` | string | Filter by user who performed action |
| `target_type` | string | Filter by target entity type (User, Reservation, etc.) |
| `start_date` | string | Start date filter |
| `end_date` | string | End date filter |
| `sort_by` | string | Sort field (default: created_at) |
| `sort_order` | string | asc or desc (default: desc) |
| `page` | integer | Page number |
| `per_page` | integer | Items per page |

**Request**:

```http
GET /audit-events?event_type=USER_LOGIN&page=1&per_page=20 HTTP/1.1
Host: localhost:5000
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...
```

**Response 200**:

```json
{
  "data": [
    {
      "id": "audit-001",
      "event_type": "USER_LOGIN",
      "actor_id": "550e8400-e29b-41d4-a716-446655440000",
      "actor_username": "alice",
      "actor_ip": "192.168.1.100",
      "target_type": null,
      "target_id": null,
      "details": null,
      "created_at": "2026-04-08T10:30:00Z"
    }
  ],
  "pagination": {
    "page": 1,
    "per_page": 20,
    "total": 1,
    "total_pages": 1,
    "has_next": false,
    "has_prev": false
  },
  "meta": {
    "request_id": "550e8400-e29b-41d4-a716-446655440000",
    "timestamp": "2026-04-08T10:30:00Z"
  }
}
```

**Error Responses**:

- `403 FORBIDDEN` - Not an org_admin

---

## Admin Endpoints

### GET /admin/system-status

Get system status (platform_admin only).

**Auth**: Required (`platform_admin` role)

**Request**:

```http
GET /admin/system-status HTTP/1.1
Host: localhost:5000
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...
```

**Response 200**:

```json
{
  "data": {
    "database": "connected",
    "scheduler": "running",
    "uptime_seconds": 86400,
    "memory_usage_mb": 125.4,
    "active_users": 15,
    "pending_jobs": 2
  },
  "meta": {
    "request_id": "550e8400-e29b-41d4-a716-446655440000",
    "timestamp": "2026-04-08T10:30:00Z"
  }
}
```

**Error Responses**:

- `403 FORBIDDEN` - Not a platform_admin

---

### GET /admin/debug/routes

List all registered Flask routes (debug endpoint).

**Auth**: Required (`platform_admin` role)

**Gate**: `ENABLE_DEBUG_ENDPOINTS=true` environment variable

**Request**:

```http
GET /admin/debug/routes HTTP/1.1
Host: localhost:5000
Authorization: Bearer eyJ0eXAToiJKV1QiLCJhbGciOiJIUzI1NiJ9...
```

**Response 200**:

```json
{
  "data": {
    "routes": [
      {
        "endpoint": "auth.login",
        "methods": ["POST"],
        "rule": "/auth/login"
      },
      {
        "endpoint": "booking.hold_reservation",
        "methods": ["POST"],
        "rule": "/reservations/hold"
      }
    ]
  },
  "meta": {
    "request_id": "550e8400-e29b-41d4-a716-446655440000",
    "timestamp": "2026-04-08T10:30:00Z"
  }
}
```

**Error Responses**:

- `403 FORBIDDEN` - Not a platform_admin
- `404 NOT_FOUND` - Debug endpoints disabled (`ENABLE_DEBUG_ENDPOINTS=false`)

---

### GET /admin/debug/config-redacted

Show application configuration with secrets redacted (debug endpoint).

**Auth**: Required (`platform_admin` role)

**Gate**: `ENABLE_DEBUG_ENDPOINTS=true` environment variable

**Request**:

```http
GET /admin/debug/config-redacted HTTP/1.1
Host: localhost:5000
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...
```

**Response 200**:

```json
{
  "data": {
    "config": {
      "APP_ENV": "development",
      "DEBUG": true,
      "SECRET_KEY": "***REDACTED***",
      "DATABASE_URL": "sqlite:////app/data/app.db",
      "JWT_SECRET_KEY": "***REDACTED***",
      "ENCRYPTION_MASTER_KEY": "***REDACTED***",
      "HOLD_EXPIRY_MINUTES": 10,
      "RATE_LIMIT_DEFAULT_PER_MINUTE": 60
    }
  },
  "meta": {
    "request_id": "550e8400-e29b-41d4-a716-446655440000",
    "timestamp": "2026-04-08T10:30:00Z"
  }
}
```

**Error Responses**:

- `403 FORBIDDEN` - Not a platform_admin
- `404 NOT_FOUND` - Debug endpoints disabled

---

## Rate Limiting

All endpoints enforce rate limiting via token bucket algorithm:

- **Default**: 60 requests/minute with burst of 20
- **Per-IP**: Public endpoints tracked by client IP
- **Per-User**: Authenticated endpoints tracked by user ID

When rate limited, the API returns:

**Response 429**:

```json
{
  "error": {
    "code": "RATE_LIMITED",
    "message": "Too many requests. Please slow down.",
    "details": {
      "retry_after_seconds": 45
    }
  },
  "meta": {
    "request_id": "550e8400-e29b-41d4-a716-446655440000",
    "timestamp": "2026-04-08T10:30:00Z"
  }
}
```

**Headers**:

```
HTTP/1.1 429 Too Many Requests
X-RateLimit-Limit: 60
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1712575845
Retry-After: 45
```

---

## Pagination

All list endpoints support pagination via query parameters:

| Parameter  | Type    | Default | Max | Description             |
| ---------- | ------- | ------- | --- | ----------------------- |
| `page`     | integer | 1       | -   | Page number (1-indexed) |
| `per_page` | integer | 20      | 100 | Items per page          |

**Pagination Response Object**:

```json
{
  "pagination": {
    "page": 2,
    "per_page": 20,
    "total": 150,
    "total_pages": 8,
    "has_next": true,
    "has_prev": true
  }
}
```

---

## Versioning

Current API version: **v1** (implicit, no version prefix in URLs)

Future versions will use path-based versioning: `/v2/auth/login`

---

## Additional Resources

- **Architecture**: See `design.md` for system architecture
- **Data Model**: See `repo/docs/data-model.md` for database schema
- **Security**: See `repo/docs/security-model.md` for security controls
- **Operations**: See `repo/docs/operational-runbook.md` for deployment guide
