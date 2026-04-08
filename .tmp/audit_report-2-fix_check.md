# Audit Report 2 - Fix Check

Date: 2026-04-08
Scope: Re-validation of issues that were **Not fixed** or **Partially fixed** in `.tmp/audit_report-1-fix_check.md`.

## Summary
- Fixed: 3
- Partially fixed: 1
- Not fixed: 0

## Issue-by-Issue Recheck

1. **Oversell protection lacks DB-level overlap constraint; race-prone logic**  
Status: **Partially fixed**
- Improvement present: `repo/src/app.py:247-258` now creates partial unique index `uix_reservation_no_overlap` on `(resource_id, start_time, end_time)` for active statuses.
- Remaining gap: this index only blocks **exact same start/end timestamps**. It does **not** enforce general interval overlap exclusion (e.g., `10:00-11:00` vs `10:30-11:30`).
- `repo/src/api/booking.py:107-133` and `565-574` still rely on application overlap checks (`with_for_update` + count) before insert.
- `repo/src/models/models.py:181-200` still has no model-level range overlap exclusion constraint.

2. **TLS required by prompt but disabled by default and not enforced**  
Status: **Fixed**
- `repo/src/config/__init__.py:25` sets `ENABLE_TLS=True`.
- `repo/docker-compose.yml:53` sets `ENABLE_TLS=true`.
- `repo/src/app.py:165-175` enforces HTTPS when TLS is enabled.
- `repo/README.md:187` now documents default as `true`.

3. **Prompt-default operational values diverge (backup retention, device cooldown)**  
Status: **Fixed**
- `repo/src/config/__init__.py:75` sets `DEVICE_BLACKLIST_RETRY_AFTER_HOURS=168`.
- `repo/src/config/__init__.py:83` sets `BACKUP_RETENTION_DAYS=14`.
- `repo/docker-compose.yml:43` and `:46` match these values.
- `repo/README.md:147` and `:160` now match runtime defaults.

4. **Documentation references non-delivered evidence files and incorrect coverage target**  
Status: **Fixed**
- Coverage target aligned: `repo/run_tests.sh:24` and `repo/README.md:244` both use `--cov=src`.
- Referenced docs now exist under `repo/docs/`:
  - `contracts.md`
  - `requirements-matrix.md`
  - `test-matrix.md`
  - `security-model.md`
  - `data-model.md`
  - `operational-runbook.md`
  - `reviewer-dry-run-template.md`

## Overall Verdict
**Mostly Pass (1 remaining partial item).**

All previously open documentation/configuration mismatches are resolved. The remaining technical risk is booking overlap race-hardening: DB enforcement currently prevents exact duplicate windows but does not enforce true interval non-overlap at the database layer.
