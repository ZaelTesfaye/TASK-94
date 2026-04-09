# Operational Runbook

Procedures for startup, migration, backup, recovery, and alert response.

## 1. Application Startup

### Prerequisites
- Docker and Docker Compose installed
- TLS certificates placed at `./certs/cert.pem` and `./certs/key.pem`
- Environment variables reviewed in `docker-compose.yml` (change all default secrets for production)

### Start the service (Docker)
```
docker compose up -d
```

### Start locally (development)
```
pip install -r src/requirements.txt
python -c "from src.app import create_app; app = create_app(); app.run(host='0.0.0.0', port=5000)"
```

### Start with Gunicorn (production without Docker)
```
gunicorn --bind 0.0.0.0:5000 --workers 1 --threads 4 'src.app:create_app()'
```

### Verify startup
```
curl -k https://localhost:5000/health
```
Expected: `{"data": {"status": "healthy", "database": "connected", ...}}`

### First boot behavior
- On first start with an empty database, `db.create_all()` creates all tables
- A default platform admin is bootstrapped (`ADMIN_USERNAME` / `ADMIN_PASSWORD`, defaults to admin/admin)
- Change the admin password immediately in production

### Configuration
- All configuration flows through `src/config/__init__.py`
- Set environment variables to override defaults; never edit code for config changes
- Sensitive keys that must be changed for production: `SECRET_KEY`, `JWT_SECRET_KEY`, `ENCRYPTION_MASTER_KEY`, `REQUEST_SIGNING_SECRET`

### TLS Certificate Generation (Development)
```
openssl req -x509 -newkey rsa:2048 -keyout certs/key.pem -out certs/cert.pem -days 365 -nodes
```
To disable TLS for local development, set `ENABLE_TLS=false`.

## 2. Database Migration

The application uses SQLAlchemy with `db.create_all()` for table creation. For schema changes:

### Adding new columns or tables
1. Update model definitions in `src/models/models.py`
2. If using Alembic (recommended for production), generate a migration:
   ```
   alembic revision --autogenerate -m "description"
   alembic upgrade head
   ```
3. Without Alembic, the app calls `db.create_all()` on startup, which creates missing tables but does not alter existing ones

### Breaking schema changes
1. Back up the database before applying changes (see section 3)
2. Apply migration during a maintenance window
3. Verify by hitting `/health` and `/admin/system-status`

## 3. Backup Procedures

### Configuration
- Backup directory: `/app/backups` (Docker volume `app-backups`)
- Retention: 14 days (configurable via `BACKUP_RETENTION_DAYS`)
- Schedule: Daily at 02:00 UTC (configurable via `BACKUP_SCHEDULE_CRON`)

### Scheduled Jobs

| Job | Interval | Description |
|---|---|---|
| Hold auto-release | 1 min | Releases expired reservation holds |
| Nonce cleanup | 10 min | Removes expired nonces from signing store |
| Denylist cleanup | 1 hour | Removes expired access token denylist entries |
| Backup | Daily 2 AM | SQLite database backup |
| Backup purge | Daily 3 AM | Removes backups older than retention period |
| Idempotency cleanup | 6 hours | Removes expired idempotency records |
| Anomaly alerts | 5 min | Evaluates login failure spikes |

### Manual backup (SQLite)
```
docker compose exec api cp /app/data/app.db /app/backups/app-$(date +%Y%m%d-%H%M%S).db
```

### Verify backup integrity
```
docker compose exec api sqlite3 /app/backups/<backup-file> "SELECT count(*) FROM users;"
```

### Export data
The API supports CSV exports via `POST /exports`. Exported files are stored in `/app/exports` (Docker volume `app-exports`).

### Backup retention cleanup
Old backups beyond `BACKUP_RETENTION_DAYS` should be removed by the scheduler or a cron job:
```
find /app/backups -name "*.db" -mtime +14 -delete
```

## 4. Recovery Procedures

### Restore from backup (SQLite)
1. Stop the service: `docker compose stop api`
2. Copy backup file over the database: `cp /app/backups/<backup-file> /app/data/app.db`
3. Restart: `docker compose start api`
4. Verify: `curl -k https://localhost:5000/health`

### Recovery from corrupted database
1. Stop the service
2. Restore the most recent verified backup
3. Review `audit_events` to assess data loss window
4. Restart and verify

### Recovery from lost encryption key
- If `ENCRYPTION_MASTER_KEY` is lost, encrypted fields (`moderation_cases.decision_notes`, `appeal_notes`, `appeal_decision_notes`, device fingerprints) cannot be decrypted
- The application will continue to function but those fields will return raw ciphertext
- There is no recovery path; key management is critical

## 5. Alert Response Procedures

### Alert severity levels

| Severity | Response SLA | Examples |
|---|---|---|
| CRITICAL | Immediate | Backup failure |
| HIGH | Within 1 hour | Login failure spike (>20 failures in 1 hour) |
| MEDIUM | Within 4 hours | Booking conflict spike on a resource (>=5 overlap conflicts in 5 minutes) |
| LOW | Next business day | (reserved for future use) |

### FAILED_LOGIN_SPIKE alert
1. Check `GET /audit-events?event_type=USER_LOGIN_FAILED` for the affected time window
2. Identify if it is a single user (targeted attack) or multiple users (credential stuffing)
3. For single user: verify the account is locked, consider manual password reset
4. For multiple users: review source IPs, consider IP-level blocking at the reverse proxy
5. Acknowledge the alert: `POST /alerts/<id>/ack`
6. Resolve after mitigation: `POST /alerts/<id>/resolve`

### BOOKING_CONFLICT_SPIKE alert
1. Check `GET /audit-events?event_type=RESERVATION_HELD` for the affected resource
2. Review whether the resource capacity or slot quotas need adjustment
3. If a single user is causing excessive holds, review for abuse
4. Acknowledge and resolve the alert

### BACKUP_FAILURE alert
1. Check disk space on backup volume: `docker compose exec api df -h /app/backups`
2. Verify file permissions on backup directory
3. Check database connectivity via `/health`
4. Manually trigger a backup and verify success
5. Acknowledge and resolve the alert

### General alert workflow
- View alerts: `GET /alerts?status=OPEN`
- Filter by severity: `GET /alerts?severity=HIGH`
- Acknowledge: `POST /alerts/<id>/ack`
- Resolve: `POST /alerts/<id>/resolve`

## 6. Environment Variables Reference

All configuration flows through `src/config/__init__.py`. Key security settings:

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | change-me | Flask secret key |
| `JWT_SECRET_KEY` | change-me | JWT signing key |
| `ENCRYPTION_MASTER_KEY` | change-me | AES-256-GCM master key |
| `REQUEST_SIGNING_SECRET` | change-me | HMAC request signing key |
| `ENABLE_TLS` | true | Enforce HTTPS (default true; only disable explicitly for test harness) |
| `LOGIN_MAX_FAILURES` | 5 | Lockout threshold |
| `CAPTCHA_THRESHOLD` | 3 | CAPTCHA trigger threshold |
| `RATE_LIMIT_DEFAULT_PER_MINUTE` | 60 | Rate limiter tokens/minute |
| `BACKUP_RETENTION_DAYS` | 14 | Backup file retention |
| `HOLD_EXPIRY_MINUTES` | 10 | Reservation hold TTL |

**All `change-me` values MUST be replaced in production.**

## 7. Monitoring Checklist

| Check | Method | Frequency |
|---|---|---|
| Service health | `GET /health` | Every 30 seconds (load balancer) |
| Database connectivity | Health endpoint `database` field | Every 30 seconds |
| Disk usage (data, exports, backups) | `docker system df`, volume inspection | Daily |
| Open alerts | `GET /alerts?status=OPEN` | Continuously (dashboard) |
| Audit event volume | `GET /audit-events` with date range | Weekly review |
| System status | `GET /admin/system-status` (platform admin) | Daily |
| TLS certificate expiry | External cert checker | Weekly |
| Backup file presence | `ls /app/backups/*.db` | Daily |

## 8. Shutdown and Maintenance

### Graceful shutdown
```
docker compose stop api
```

### Full teardown (preserves volumes)
```
docker compose down
```

### Full teardown including data
```
docker compose down -v
```
Warning: This destroys all database, export, and backup data.
