# System Design & Architecture

Complete architecture documentation for the Learning & Resource Booking Governance API.

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Layered Architecture](#layered-architecture)
3. [Directory Structure](#directory-structure)
4. [Key Design Decisions](#key-design-decisions)
5. [Technology Stack](#technology-stack)
6. [Data Flow](#data-flow)
7. [Security Architecture](#security-architecture)
8. [Deployment Model](#deployment-model)

---

## Architecture Overview

### System Purpose

The Learning & Resource Booking Governance API is a single-node, offline, Dockerized Flask application designed for local deployment with complete governance capabilities. It provides:

- **Authentication & Authorization**: Local username/password authentication with JWT tokens and RBAC
- **Resource Booking**: Two-phase reservation system with conflict prevention and automatic expiry
- **Content Management**: User-generated content with quality ratings and moderation workflow
- **Analytics**: Learning behavior tracking and course effectiveness metrics
- **Audit & Compliance**: Complete audit trail with alert system
- **Data Export**: Async job-based export system with deduplication

### Core Principles

1. **Zero External Dependencies**: No external APIs, third-party services, or network calls
2. **Offline-First**: Fully functional without internet connectivity
3. **Single-Node**: No distributed systems complexity; all state in one SQLite database
4. **Docker-First**: One-command startup via `docker-compose up`
5. **Security by Default**: RBAC, encryption at rest, request signing, rate limiting

### System Boundaries

```
┌─────────────────────────────────────────────────────────┐
│                    Docker Container                      │
│                                                          │
│  ┌────────────────────────────────────────────────┐    │
│  │           Flask Application (Python)            │    │
│  │                                                 │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐    │    │
│  │  │   API    │  │ Business │  │   Data   │    │    │
│  │  │  Layer   │→ │  Logic   │→ │  Access  │    │    │
│  │  └──────────┘  └──────────┘  └──────────┘    │    │
│  │                                                 │    │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐    │    │
│  │  │ Security │  │ Scheduler│  │  Logging │    │    │
│  │  │  Layer   │  │  (APSch) │  │  System  │    │    │
│  │  └──────────┘  └──────────┘  └──────────┘    │    │
│  └────────────────────────────────────────────────┘    │
│                           ↓                              │
│  ┌────────────────────────────────────────────────┐    │
│  │           SQLite Database (File-based)          │    │
│  │              /app/data/app.db                   │    │
│  └────────────────────────────────────────────────┘    │
│                                                          │
│  Volumes: /app/data, /app/exports, /app/backups        │
└─────────────────────────────────────────────────────────┘
```

---

## Layered Architecture

The application follows a strict layered architecture with clear separation of concerns:

### Layer 1: API Layer (`src/api/`)

**Responsibility**: HTTP request/response handling, input validation, response formatting

**Components**:

- Blueprint modules for each domain (auth, booking, content, analytics, etc.)
- Request parsing and validation using Flask's request object
- Response envelope construction (success/error wrapper with metadata)
- HTTP status code mapping

**Key Files**:

- `src/api/auth.py` - Authentication endpoints
- `src/api/booking.py` - Resource booking endpoints
- `src/api/content.py` - Content management endpoints
- `src/api/admin.py` - Admin/debug endpoints
- `src/api/permissions.py` - Permission management
- `src/api/invitations.py` - Invitation system
- `src/api/analytics.py` - Analytics queries
- `src/api/audit.py` - Audit log access

**No Direct Database Access**: This layer MUST NOT import or use SQLAlchemy models directly for write operations. Reads are permitted for simple queries.

### Layer 2: Business Logic Layer (`src/services/`, `src/security/`)

**Responsibility**: Domain logic, business rules, state transitions, security enforcement

**Components**:

- State machines (booking status, content quality, moderation workflow)
- Business rule enforcement (quota limits, conflict detection, rating thresholds)
- Security services (password hashing, token generation, encryption, signing)
- Idempotency enforcement
- Duplicate detection

**Key Files**:

- `src/security/passwords.py` - Argon2id password hashing
- `src/security/tokens.py` - JWT creation and validation
- `src/security/encryption.py` - AES-256-GCM field encryption
- `src/security/lockout.py` - Account lockout and captcha logic
- `src/security/rate_limiter.py` - Token bucket rate limiting
- `src/security/signing.py` - HMAC request signature validation

**No HTTP Concerns**: This layer does not know about Flask, requests, or responses.

### Layer 3: Data Access Layer (`src/models/`)

**Responsibility**: Database schema, ORM mappings, data persistence

**Components**:

- SQLAlchemy model definitions
- Relationships and foreign keys
- Database constraints (unique, not null, check constraints)
- Enum definitions

**Key Files**:

- `src/models/models.py` - All ORM model classes (15 core tables)
- `src/models/base.py` - SQLAlchemy instance and base class
- `src/models/enums.py` - All enumeration types

**Pure Data**: No business logic in models; only data structure definitions.

### Cross-Cutting Concerns

#### Configuration (`src/config/`)

- Single source of truth for all environment variables
- Type-safe configuration class
- **Zero direct `os.getenv()` calls in application code**

#### Logging (`src/logging/`)

- Centralized structured logger
- Format: `[domain][sub-domain] message`
- Automatic redaction of sensitive fields

#### Middleware (`src/security/auth_middleware.py`)

- `@require_auth` decorator for protected endpoints
- JWT validation and token denylist checking
- Permission enforcement
- Request context population (`g.current_user`)

#### Utilities (`src/utils/`)

- `responses.py` - Standard envelope wrappers
- `pagination.py` - Pagination helper
- `validators.py` - Input validation functions

---

## Directory Structure

```
repo/
├── src/                          # Application source code
│   ├── api/                      # Layer 1: API endpoints (Blueprints)
│   │   ├── auth.py               # POST /auth/login, /auth/register, etc.
│   │   ├── booking.py            # POST /reservations/hold, /reservations/{id}/confirm
│   │   ├── content.py            # POST /content, GET /content, ratings, comments
│   │   ├── permissions.py        # RBAC permission management
│   │   ├── invitations.py        # Invitation code system
│   │   ├── analytics.py          # Learning analytics queries
│   │   ├── audit.py              # Audit event log access
│   │   ├── admin.py              # Admin/debug endpoints (gated)
│   │   └── health.py             # GET /health
│   │
│   ├── models/                   # Layer 3: Data access (ORM models)
│   │   ├── models.py             # SQLAlchemy model definitions
│   │   ├── base.py               # db instance
│   │   └── enums.py              # Enum types
│   │
│   ├── security/                 # Layer 2: Security modules
│   │   ├── passwords.py          # Argon2id hashing
│   │   ├── tokens.py             # JWT creation/validation
│   │   ├── encryption.py         # AES-256-GCM encryption
│   │   ├── lockout.py            # Account lockout + captcha
│   │   ├── rate_limiter.py       # Token bucket rate limiting
│   │   ├── signing.py            # HMAC request signing
│   │   └── auth_middleware.py    # @require_auth decorator
│   │
│   ├── services/                 # Layer 2: Business logic (future)
│   │   └── (reserved for complex business logic)
│   │
│   ├── config/                   # Cross-cutting: Configuration
│   │   └── __init__.py           # Config class with all env vars
│   │
│   ├── logging/                  # Cross-cutting: Logging
│   │   └── __init__.py           # Structured logger instance
│   │
│   ├── utils/                    # Cross-cutting: Utilities
│   │   ├── responses.py          # success_response(), error_response()
│   │   ├── pagination.py         # paginate() helper
│   │   └── validators.py         # Input validation helpers
│   │
│   ├── scheduler/                # Background jobs
│   │   └── __init__.py           # APScheduler setup (hold expiry, backups)
│   │
│   ├── tests/                    # Test suites
│   │   ├── unit/                 # Unit tests (business logic, security)
│   │   └── api/                  # API integration tests
│   │
│   ├── app.py                    # Application factory (create_app)
│   ├── Dockerfile                # Container build instructions
│   └── requirements.txt          # Python dependencies
│
├── migrations/                   # Alembic database migrations
│   ├── env.py                    # Migration environment
│   ├── script.py.mako            # Migration template
│   └── versions/                 # Versioned migration scripts
│
├── scripts/                      # Utility scripts
│   ├── generate-certs.sh         # TLS certificate generation (Linux/macOS)
│   └── generate-certs.ps1        # TLS certificate generation (Windows)
│
├── docs/                         # Technical documentation
│   ├── contracts.md              # Full API contract reference
│   ├── data-model.md             # Database schema documentation
│   ├── security-model.md         # Security controls documentation
│   ├── operational-runbook.md    # Operations guide
│   ├── requirements-matrix.md    # Requirements traceability
│   └── test-matrix.md            # Test coverage matrix
│
├── docker-compose.yml            # Container orchestration
├── .env.example                  # Environment variable template
├── alembic.ini                   # Alembic configuration
├── run_tests.sh                  # Test execution script
└── README.md                     # Quick start guide
```

---

## Key Design Decisions

### Decision 1: SQLite Instead of PostgreSQL

**Choice**: Single SQLite file database

**Rationale**:

- **Simplicity**: No separate database container or service to manage
- **Zero Config**: Database created automatically on first startup
- **Portability**: Entire database state in one file (`app.db`)
- **Adequate for Use Case**: Single-node, local deployment with moderate load
- **Backup Simplicity**: File-based backups via simple copy operations

**Trade-offs**:

- Limited concurrency (write serialization)
- No horizontal scaling (acceptable for offline/local use)
- Weaker type system compared to PostgreSQL

### Decision 2: No External Services (Payment, Email, SMS)

**Choice**: All external service integrations are stubbed/mocked

**Rationale**:

- **Offline Requirement**: System must function without internet
- **Audit Stability**: No external service failures during QA review
- **Reproducibility**: Consistent behavior across all environments

**Implementation**:

- Payment processing: Stubbed with success responses
- Email delivery: Logged only, no actual sending
- SMS/Captcha: In-memory challenge storage

### Decision 3: Two-Phase Booking System

**Choice**: Hold → Confirm pattern instead of direct booking

**Rationale**:

- **Conflict Prevention**: Hold prevents race conditions during user decision-making
- **User Experience**: User can review booking details before final confirmation
- **Automatic Cleanup**: Expired holds released by scheduler (no orphaned reservations)

**Implementation**:

- `POST /reservations/hold` - Creates reservation in `HELD` status with TTL
- `POST /reservations/{id}/confirm` - Transitions to `CONFIRMED` with version check
- Scheduler job runs every 60 seconds to expire holds past TTL

### Decision 4: Token Bucket Rate Limiting

**Choice**: Per-IP and per-identity token bucket algorithm

**Rationale**:

- **DDoS Protection**: Prevents brute-force login attempts
- **Fairness**: Allows bursts while enforcing steady-state limits
- **State Persistence**: Bucket state in database (survives restarts)

**Configuration**:

- Default: 60 requests/minute with burst of 20
- Separate buckets for public IPs and authenticated users

### Decision 5: Idempotency via Request Headers

**Choice**: Require `Idempotency-Key` header on all state-changing booking operations

**Rationale**:

- **Network Resilience**: Client retries don't create duplicate bookings
- **Race Condition Prevention**: Concurrent requests with same key deduplicated
- **Standard Practice**: Aligns with Stripe, AWS, and other industry standards

**Implementation**:

- 24-hour deduplication window
- Stored in `idempotency_keys` table
- Returns cached response if key already processed

### Decision 6: Argon2id for Password Hashing

**Choice**: Argon2id instead of bcrypt or PBKDF2

**Rationale**:

- **Modern Standard**: Winner of Password Hashing Competition (2015)
- **Memory-Hard**: Resistant to GPU/ASIC cracking
- **Side-Channel Resistance**: Argon2id variant balances timing and memory hardness

**Configuration**:

- Time cost: 2 iterations
- Memory cost: 65536 KB (64 MB)
- Parallelism: 4 threads

### Decision 7: Request Signing (Anti-Replay)

**Choice**: HMAC-SHA256 request signing with nonce + timestamp

**Rationale**:

- **Replay Prevention**: Each request is single-use (nonce enforcement)
- **Timestamp Validation**: Rejects requests outside ±5 minute window
- **MITM Protection**: Signature covers method, path, timestamp, nonce, body

**Trade-offs**:

- Clock synchronization required (handled via skew tolerance)
- Client complexity (must implement signing logic)

### Decision 8: AES-256-GCM for Encryption at Rest

**Choice**: AES-256-GCM with HKDF key derivation

**Rationale**:

- **AEAD**: Authenticated encryption (integrity + confidentiality)
- **Performance**: Hardware acceleration on modern CPUs (AES-NI)
- **Standard**: NIST-approved algorithm

**Implementation**:

- Master key from environment variable
- Per-field key derivation using HKDF-SHA256
- Random 12-byte IV per encryption operation
- Domain separation via context parameter

---

## Technology Stack

### Backend Framework

**Flask 3.1.0**

- Lightweight WSGI framework
- Blueprint support for modular routing
- Extensive ecosystem (extensions available)
- Simple to test and deploy

**Why Flask over Django/FastAPI?**

- Lower complexity for API-only application
- No built-in ORM friction (SQLAlchemy integration cleaner)
- Faster startup and smaller footprint

### Database

**SQLite 3.39+** (via SQLAlchemy)

- File-based relational database
- ACID compliance
- JSON support for flexible fields
- Full-text search via FTS5

**SQLAlchemy 2.0.36**

- Industry-standard ORM
- Migration support via Alembic
- Connection pooling
- Query optimization

### Security Libraries

| Library      | Version | Purpose                            |
| ------------ | ------- | ---------------------------------- |
| argon2-cffi  | 23.1.0  | Password hashing (Argon2id)        |
| PyJWT        | 2.10.1  | JSON Web Token creation/validation |
| cryptography | 44.0.0  | AES-256-GCM encryption, HKDF, HMAC |

### Background Jobs

**APScheduler 3.10.4**

- In-process background job scheduler
- Cron-like scheduling syntax
- Persistent job state (survives restarts)

**Scheduled Jobs**:

- `expire_holds` - Every 60 seconds (releases expired booking holds)
- `cleanup_expired_tokens` - Every hour (purges expired refresh tokens)
- `database_backup` - Daily at 2 AM (SQLite file backup)

### Testing

**pytest 8.3.4 + pytest-cov 6.0.0**

- Unit tests for business logic
- API integration tests
- Code coverage reporting (target: ≥90%)

### HTTP Server

**Gunicorn 23.0.0** (production)

- Pre-fork worker model
- Graceful worker restarts
- Compatible with Flask WSGI app

### Containerization

**Docker + Docker Compose**

- Single-container deployment
- Volume mapping for data persistence
- Port exposure on 5000
- Environment variable injection

---

## Data Flow

### Example Flow: User Login

```
1. Client Request
   POST /auth/login
   Headers: None (public endpoint)
   Body: {"username": "alice", "password": "secret123"}

   ↓

2. API Layer (src/api/auth.py)
   - Parse JSON body
   - Extract username, password
   - Validate required fields

   ↓

3. Security Layer (src/security/lockout.py)
   - Check if account is locked out
   - Check if captcha required (failed attempt count)

   ↓

4. Data Access Layer (src/models/models.py)
   - Query User by username
   - Retrieve password_hash

   ↓

5. Security Layer (src/security/passwords.py)
   - verify_password(input_password, stored_hash)
   - Returns True/False

   ↓

6. Decision Point
   If password correct:
     ↓
     Security Layer (src/security/tokens.py)
     - create_access_token(user_id, username, role, permissions)
     - create_refresh_token(user_id)

     ↓

     Data Access Layer
     - INSERT into refresh_tokens (hash of refresh token)
     - INSERT into audit_events (USER_LOGIN)
     - COMMIT transaction

     ↓

     API Layer
     - Wrap tokens in success_response()
     - Return HTTP 200 with JSON body

   If password incorrect:
     ↓
     Security Layer (src/security/lockout.py)
     - record_failure(username)
     - Increment failure count

     ↓

     API Layer
     - Return error_response("INVALID_CREDENTIALS", HTTP 401)

7. Client Response
   HTTP 200 OK
   {
     "data": {
       "access_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
       "refresh_token": "refresh_abc123...",
       "expires_in": 1800,
       "user": {"id": "...", "username": "alice", "role": "guest"}
     },
     "meta": {
       "request_id": "uuid-v4",
       "timestamp": "2026-04-08T10:30:00Z"
     }
   }
```

### Example Flow: Protected Endpoint (Create Reservation)

```
1. Client Request
   POST /reservations/hold
   Headers:
     Authorization: Bearer <access_token>
     Idempotency-Key: unique-key-123
   Body: {
     "resource_id": "res-001",
     "start_time": "2026-04-10T14:00:00Z",
     "end_time": "2026-04-10T15:00:00Z",
     "organization_id": "org-001"
   }

   ↓

2. Middleware (src/security/auth_middleware.py)
   - Extract Bearer token from Authorization header
   - decode_token(access_token)
   - Check token denylist (revoked tokens)
   - Populate g.current_user with decoded claims

   ↓

3. API Layer (src/api/booking.py)
   - Validate Idempotency-Key header present
   - Check idempotency store for duplicate key

   If duplicate found:
     - Return cached response (HTTP 409 or original success)

   If new key:
     ↓

4. Business Logic
   - Validate resource exists and belongs to organization
   - Check user has access to organization
   - Validate time range (start < end, not in past)
   - Query existing reservations for time overlap
   - Check slot quota availability
   - Check user's active hold count

   ↓

5. Data Access Layer
   - BEGIN transaction
   - INSERT into reservations (status=HELD, version=1, expires_at=now+10min)
   - INSERT into idempotency_keys (key, response_hash)
   - INSERT into audit_events (RESERVATION_CREATED)
   - COMMIT transaction

   ↓

6. API Layer
   - Wrap reservation in success_response()
   - Return HTTP 201 Created

7. Background Scheduler (after 10 minutes if not confirmed)
   - expire_holds() job finds reservation with expires_at < now
   - UPDATE reservations SET status='EXPIRED', updated_at=now
   - INSERT into audit_events (HOLD_EXPIRED)
```

### Request Context Flow

Every request passes through:

1. **Flask Request Handler** - Parses HTTP request
2. **Before Request Hook** - Generates request_id, logs request
3. **Auth Middleware** (if protected) - Validates JWT, populates g.current_user
4. **Rate Limiter** - Checks token bucket, updates bucket state
5. **Blueprint Handler** - Business logic execution
6. **After Request Hook** - Adds response headers, logs response
7. **Error Handler** (if exception) - Converts exception to JSON error envelope

---

## Security Architecture

### Defense in Depth

The system employs multiple security layers:

1. **Transport Layer**: TLS 1.2+ (optional, configurable via `ENABLE_TLS`)
2. **Authentication Layer**: JWT access tokens (30-min expiry) + refresh tokens (14-day expiry)
3. **Authorization Layer**: Role-based access control (platform_admin, org_admin, member, guest)
4. **Request Layer**: HMAC signature validation, nonce-based replay prevention
5. **Application Layer**: Input validation, SQL injection prevention (parameterized queries)
6. **Data Layer**: Encryption at rest for sensitive fields (AES-256-GCM)
7. **Rate Limiting**: Token bucket per IP and per user

### Security Controls Matrix

| Threat               | Control                           | Implementation                    |
| -------------------- | --------------------------------- | --------------------------------- |
| Brute Force Login    | Account lockout + captcha         | `src/security/lockout.py`         |
| Token Theft          | Short expiry + denylist           | 30-min access token TTL           |
| Replay Attack        | Nonce + timestamp validation      | `src/security/signing.py`         |
| SQL Injection        | Parameterized queries             | SQLAlchemy ORM                    |
| XSS                  | JSON-only API (no HTML rendering) | Flask jsonify()                   |
| CSRF                 | Stateless tokens (no cookies)     | JWT in Authorization header       |
| Data Breach          | Encryption at rest                | AES-256-GCM for PII fields        |
| DDoS                 | Rate limiting                     | Token bucket with burst allowance |
| Privilege Escalation | RBAC enforcement                  | `@require_auth(permission="...")` |

---

## Deployment Model

### Single-Node Architecture

The system is designed for **single-node, offline deployment**:

- One Docker container runs the entire application
- One SQLite file contains all state
- No external network dependencies
- No service discovery or load balancing required

### Scaling Limitations

**NOT designed for**:

- Horizontal scaling (multi-instance deployment)
- High concurrency (SQLite write serialization)
- Distributed transactions
- Multi-region deployment

**Acceptable use cases**:

- Local development
- Small team collaboration (< 50 concurrent users)
- Offline/air-gapped environments
- Embedded systems

### Data Persistence

Three Docker volumes ensure data survives container restarts:

```yaml
volumes:
  app-data: # SQLite database file (/app/data/app.db)
  app-exports: # CSV export files (/app/exports/)
  app-backups: # Database backup files (/app/backups/)
```

### Backup Strategy

- **Automated Daily Backups**: Scheduler copies `app.db` to `/app/backups/` at 2 AM
- **Retention**: 30 days (configurable via `BACKUP_RETENTION_DAYS`)
- **Manual Backup**: `docker cp` the entire `app-data` volume

### Monitoring

- **Health Endpoint**: `GET /health` returns database connectivity and scheduler state
- **Audit Log**: All state changes logged to `audit_events` table
- **Alerts**: System alerts in `alerts` table (high login failures, quota exceeded, etc.)

---

## Conclusion

This architecture prioritizes **simplicity, security, and offline operability** over scalability. The strict layered design ensures maintainability, while the comprehensive security controls provide defense in depth suitable for a governance-focused application.

For API contracts, see `api-spec.md`.  
For data schema, see `repo/docs/data-model.md`.  
For security details, see `repo/docs/security-model.md`.
