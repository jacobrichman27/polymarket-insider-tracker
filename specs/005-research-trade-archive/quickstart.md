# Quickstart: Research Trade Archive (Phase A0)

**Feature**: `specs/005-research-trade-archive`  
**Date**: 2026-11-18  
**Purpose**: Validation scenarios that prove A0 contracts after implement. Not a substitute for `tasks.md`.

## Prerequisites

```bash
uv sync --locked --all-extras --python 3.13
cp .env.example .env
docker compose up -d postgres redis
```

Apply migrations (services profile / documented alembic path from slice 002 quickstart).

## 1. Monitor-only default (upgrade safety)

Leave `ARCHIVE_ENABLED` unset/false.

```bash
uv run python -m polymarket_insider_tracker --config-check
uv run python -m polymarket_insider_tracker --dry-run --health-port 8088
curl -s http://127.0.0.1:8088/ready
```

**Expect:** ready components are `database`, `redis`, `ingestion` only — **no** `trade_archive`. Checkpoint behavior matches pre-A0 monitor-only retain rules.

## 2. Enable archive (migration note)

Set in `.env`:

```bash
ARCHIVE_ENABLED=true
ARCHIVE_RAW_RETENTION=true
```

Restart with dry-run. **Expect:** `/ready` includes `trade_archive`. First successful archive-enabled collection persists `archive_start_at` (query `archive_collector_state` or documented status surface).

## 3. Deterministic tape + fan-out tests

After implement, run the slice’s archive-focused suites (exact module paths land in `tasks.md`), covering at least:

- Quiet fill appears on `trades` without a `risk_assessments` row
- Idempotent re-delivery (no duplicate PK)
- Archive fail → Monitor still called → identity not retained → checkpoint stalls
- Archive ok → Monitor raises → identity retained
- Crash-between insert and retain → re-deliver no-op + retain
- Ingest loss Redis push → durable `ingest_gap_events` row
- Write failure abandon path
- `trade_archive` degraded/down SLO thresholds with fake clock
- Assessment persist failure does not mark tape down / does not block alert attempt

Prefer:

```bash
uv run python scripts/verify.py --profile static
uv run --env-file .env python scripts/verify.py --profile services
```

## 4. Capacity smoke (ops)

Confirm partitions exist for today + ahead; disk/alarm hooks documented. Record provisional budget used for the deployment (see plan / Data.md).

## 5. Planes check

Confirm docs/config offer no place/cancel/order paths. Reserved future consumer remains unwired.
