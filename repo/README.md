# Learning & Resource Booking Governance API

A single-node, offline, Dockerized Flask API for learning management and resource booking with full governance. Designed for local deployment with no external service dependencies, providing authentication, role-based access control, booking with conflict prevention, content moderation, analytics, audit trails, and automated backups -- all backed by SQLite.

---

## Table of Contents

- [Quick Start](#quick-start)
- [Setup - Local Development (without Docker)](#setup---local-development-without-docker)
- [TLS Local Setup](#tls-local-setup)
- [Configuration Variables](#configuration-variables)
- [Migration Commands](#migration-commands)
- [Run Commands](#run-commands)
- [Test Commands](#test-commands)
- [Route Group Inventory](#route-group-inventory)
- [Role Model Summary](#role-model-summary)
- [Security Model Summary](#security-model-summary)
- [Known Limitations and Manual Verification Boundaries](#known-limitations-and-manual-verification-boundaries)
- [Static Evidence Index](#static-evidence-index)

---

## Quick Start

```bash
docker-compose up --build
```

The API runs at http://localhost:5000. Default admin credentials: username=`admin`, password=`admin`. Override `ADMIN_PASSWORD` via environment variable before deploying to production — the application will refuse to start in non-development environments with the default password.

---

## Setup - Local Development (without Docker)

```bash
cd repo
pip install -r src/requirements.txt
python -c "from src.app import create_app; app = create_app(); app.run(host='0.0.0.0', port=5000)"
```

---

## TLS Local Setup

Generate self-signed certificates for local HTTPS:

```bash
# Linux/macOS
./scripts/generate-certs.sh

# Windows
powershell ./scripts/generate-certs.ps1
```

TLS is enabled by default. Certificates are mounted read-only at `/app/certs/`. To disable TLS for local development, set `ENABLE_TLS=false`.

---

## Configuration Variables

All environment variables are defined in `docker-compose.yml`. Defaults are development-safe. Override via `.env` file or direct environment injection.

### Application

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `APP_ENV` | string | `development` | Application environment (`development`, `production`) |
| `DEBUG` | bool | `false` | Enable debug mode and verbose error output. Disable in production. |
| `SECRET_KEY` | string | `dev-secret-key-change-in-production` | Flask secret key for session and CSRF support |

### Database

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `DATABASE_URL` | string | `sqlite:////app/data/app.db` | SQLAlchemy database connection URI |

### JWT

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `JWT_SECRET_KEY` | string | `jwt-dev-secret-change-in-production` | Secret key for JWT signing |
| `JWT_ACCESS_TOKEN_EXPIRES_MINUTES` | int | `30` | Access token lifetime in minutes |
| `JWT_REFRESH_TOKEN_EXPIRES_DAYS` | int | `14` | Refresh token lifetime in days |
| `JWT_ALGORITHM` | string | `HS256` | JWT signing algorithm |
| `JWT_ISSUER` | string | `learning-booking-api` | JWT issuer claim value |

### Encryption

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ENCRYPTION_MASTER_KEY` | string | `dev-master-key-32-bytes-change-me` | Master key for AES-256-GCM encryption at rest (minimum 32 bytes) |

### Request Signing

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `REQUEST_SIGNING_SECRET` | string | `dev-signing-secret-change-me` | HMAC-SHA256 shared secret for request signing |
| `REQUEST_SIGNING_SKEW_SECONDS` | int | `300` | Maximum allowed clock skew for signed requests (seconds) |
| `NONCE_RETENTION_SECONDS` | int | `600` | Duration to retain nonces for replay prevention (seconds) |

### Rate Limiting

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `RATE_LIMIT_DEFAULT_PER_MINUTE` | int | `60` | Default request rate limit per minute |
| `RATE_LIMIT_BURST` | int | `20` | Maximum burst allowance above steady rate |

### Login Security

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `LOGIN_MAX_FAILURES` | int | `5` | Failed login attempts before account lockout |
| `LOGIN_LOCKOUT_MINUTES` | int | `15` | Lockout duration after max failed attempts (minutes) |
| `CAPTCHA_THRESHOLD` | int | `3` | Failed attempts before captcha challenge is required |

### Booking

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `HOLD_EXPIRY_MINUTES` | int | `10` | Duration before a held reservation auto-releases (minutes) |
| `BOOKING_BUFFER_MINUTES` | int | `5` | Buffer time after a booking ends before slot is available (minutes) |
| `MAX_ACTIVE_HOLDS_PER_USER` | int | `3` | Maximum concurrent held reservations per user |
| `DEFAULT_SLOT_QUOTA` | int | `1` | Default number of concurrent bookings per slot |
| `IDEMPOTENCY_WINDOW_HOURS` | int | `24` | Idempotency key deduplication window (hours) |

### Content

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `RATING_DEMOTION_MIN_COUNT` | int | `20` | Minimum rating count before demotion evaluation |
| `RATING_DEMOTION_THRESHOLD` | float | `2.0` | Average rating below which content is demoted |
| `APPEAL_WINDOW_DAYS` | int | `7` | Days allowed to appeal a moderation decision |
| `APPEAL_MIN_NOTES_LENGTH` | int | `50` | Minimum character length for appeal justification |

### Invitation

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `INVITATION_EXPIRY_HOURS` | int | `72` | Invitation code validity period (hours) |

### Device

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `DEVICE_RISK_BLACKLIST_THRESHOLD` | float | `0.9` | Risk score threshold to auto-blacklist a device |
| `DEVICE_RISK_INCREMENT_PER_FAILURE` | float | `0.15` | Risk score increment per failed login attempt |
| `DEVICE_BLACKLIST_RETRY_AFTER_HOURS` | int | `168` | Hours before a blacklisted device may retry (default: 7 days) |

### Export

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `EXPORT_DIR` | string | `/app/exports` | Directory for generated CSV export files |

### Backup

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `BACKUP_DIR` | string | `/app/backups` | Directory for database backup files |
| `BACKUP_RETENTION_DAYS` | int | `14` | Number of days to retain backup files |
| `BACKUP_SCHEDULE_CRON` | string | `0 2 * * *` | Cron expression for automated backup schedule |

### Logging

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `LOG_LEVEL` | string | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`) |
| `LOG_FORMAT` | string | `structured` | Log output format (`structured`, `plain`) |

### Pagination

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `DEFAULT_PAGE_SIZE` | int | `20` | Default number of items per page for list endpoints |
| `MAX_PAGE_SIZE` | int | `100` | Maximum allowed items per page |

### Admin Bootstrap

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ADMIN_USERNAME` | string | `admin` | Bootstrap platform admin username. |
| `ADMIN_PASSWORD` | string | `admin` | Bootstrap platform admin password. **Must be overridden in production** (`APP_ENV != development`); the application will refuse to start if the default remains. |

### Admin / Debug

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ENABLE_DEBUG_ENDPOINTS` | bool | `false` | Enable debug endpoints (routes, config inspection). Disable in production. |

### TLS

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `ENABLE_TLS` | bool | `true` | Enable HTTPS. Required in production. Set to `false` only for local development. |
| `TLS_CERT_PATH` | string | `/app/certs/cert.pem` | Path to TLS certificate file |
| `TLS_KEY_PATH` | string | `/app/certs/key.pem` | Path to TLS private key file |

### Timezone

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `TIMEZONE` | string | `UTC` | Server timezone for scheduling and timestamp normalization |

---

## Migration Commands

```bash
# Generate a new migration
alembic revision --autogenerate -m "description"

# Run all pending migrations
alembic upgrade head
```

Note: Tables are auto-created on first startup via `db.create_all()` for development convenience. For production deployments, use Alembic migrations exclusively.

---

## Run Commands

```bash
# Development (with Docker) — TLS disabled, runs at http://localhost:5000
docker-compose up --build

# Production (with TLS) — uses docker-compose.tls.yml overlay with gunicorn TLS termination
docker-compose -f docker-compose.yml -f docker-compose.tls.yml up --build -d

# Direct (no Docker)
gunicorn --bind 0.0.0.0:5000 "src.app:create_app()"
```

---

## Test Commands

```bash
# All tests
./run_tests.sh

# Or directly with pytest
python -m pytest tests/ -v

# Unit tests only
python -m pytest tests/unit/ -v

# API/Integration tests only
python -m pytest tests/api/ -v

# With coverage
python -m pytest tests/ --cov=src --cov-report=term-missing
```

---

## Route Group Inventory

| Group | Prefix | Description |
|-------|--------|-------------|
| Auth | `/auth` | Registration, login, logout, refresh, device binding |
| Permissions | `/permissions` | Permission CRUD, assignment, memberships |
| Invitations | `/invitations` | Invitation lifecycle |
| Booking | `/resources`, `/slot-templates`, `/reservations`, `/availability` | Resource and reservation management |
| Content | `/content`, `/moderation` | Content governance and moderation |
| Analytics | `/analytics` | Learning behavior, completion, difficulty, effectiveness |
| Exports | `/exports` | CSV data export and download |
| Audit | `/audit-events`, `/alerts` | Audit trail and alert management |
| Admin | `/admin` | System status, debug endpoints |
| Health | `/health` | Health check |

---

## Role Model Summary

| Role | Level | Capabilities |
|------|-------|-------------|
| `guest` | 0 | Register, view public content |
| `member` | 1 | Full booking, content interaction, analytics |
| `org_admin` | 2 | Manage org resources, users, invitations, moderation |
| `platform_admin` | 3 | Full system access, cross-org, debug endpoints |

---

## Security Model Summary

- **Password hashing**: Argon2id with per-user salt
- **Encryption at rest**: AES-256-GCM with HKDF-SHA256 key derivation and per-field IV
- **JWT authentication**: Access and refresh tokens with rotation and revocation
- **Request signing**: HMAC-SHA256 over method, path, timestamp, nonce, and body hash
- **Rate limiting**: Per-IP and per-identity buckets with configurable burst allowance
- **Login security**: Account lockout after configurable failed attempts; captcha challenge gate
- **Role-based access control**: 4-tier hierarchy (guest, member, org_admin, platform_admin) with least-privilege defaults
- **Object-level authorization**: Ownership and org-scope checks on every loaded resource
- **Tenant isolation**: All queries constrained by organization context unless platform_admin

---

## Known Limitations and Manual Verification Boundaries

- **SQLite single-writer limitation**: SQLite does not support true concurrent writes. Write serialization is enforced via `BEGIN IMMEDIATE` transactions.
- **Hold auto-release depends on scheduler**: The hold expiry job must be running for automatic release. Testable with manual time manipulation in unit tests.
- **TLS certificate generation requires openssl on host**: The cert generation scripts depend on `openssl` being available in the host environment.
- **Backup scheduler tested via unit test**: Runtime cron execution verification is manual. The backup job logic is covered by unit tests, but actual scheduled execution in Docker requires manual observation.
- **Export CSV generation is synchronous**: Suitable for moderate dataset sizes. Large exports may block the request thread.
- **No email/SMS delivery**: Invitation codes are returned directly in the API response. There is no external notification mechanism.

---

## Static Evidence Index

| Document | Path | Description |
|----------|------|-------------|
| API Contracts | `../docs/contracts.md` | Full API endpoint contracts with request/response schemas |
| Requirement Traceability | `../docs/requirements-matrix.md` | Prompt and question requirements mapped to code and tests |
| Test Coverage Matrix | `../docs/test-matrix.md` | Risk points mapped to test files and coverage status |
| Security Architecture | `../docs/security-model.md` | Security controls, threat model, and implementation details |
| Data Model Reference | `../docs/data-model.md` | Database schema, constraints, and relationship documentation |
| Operations Guide | `../docs/operational-runbook.md` | Deployment, backup, monitoring, and incident procedures |
| Reviewer Dry-Run | `../docs/reviewer-dry-run-template.md` | Section-by-section review checklist with decision placeholders |
