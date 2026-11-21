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

Apply migrations (services profile / documented alembic path from slice 002 quickstart). Alembic revision: `005_research_trade_archive_a0`.

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

Restart with dry-run. **Expect:** `/ready` includes `trade_archive`. First successful archive-enabled collection persists `archive_start_at` (query `archive_collector_state`). Dry-run **still writes** the `trades` tape and gap ledger; it only suppresses real Discord/Telegram delivery.

## 3. Deterministic tape + fan-out tests

Focused suites (run from repo root):

```bash
.venv/bin/python -m pytest \
  tests/storage/test_archive_writer.py \
  tests/ingestor/test_archive_writer.py \
  tests/ingestor/test_archive_dry_run.py \
  tests/ingestor/test_trade_poller_archive_fanout.py \
  tests/ingestor/test_trade_poller_archive_stall.py \
  tests/ingestor/test_archive_abandon.py \
  tests/storage/test_ingest_gap_events.py \
  tests/ingestor/test_gap_ledger_mirror.py \
  tests/ingestor/test_trade_archive_health.py \
  tests/ingestor/test_trade_archive_assessment_isolation.py \
  tests/ingestor/test_archive_capacity_signals.py \
  tests/test_archive_no_execution_surface.py \
  tests/ingestor/test_archive_collector_state.py \
  -q
```

Coverage includes: quiet fill without `risk_assessments`; idempotent insert; dry-run×archive; fan-out isolation; stall + backoff; abandon-when-unreachable; gap ledger + Redis loss mirror; tape SLOs; assessment persist ≠ tape down; partition-miss / insert-rate metrics; no execution config surface.

Prefer full gates:

```bash
uv run python scripts/verify.py --profile static
uv run --env-file .env python scripts/verify.py --profile services
```

## 4. Capacity smoke (ops)

Confirm daily partitions exist for today ± ahead; alarm if missing. Disk ≥70% of the documented provisional budget is an **ops/host** alarm (not in-process). See plan / `Data.md` Provisional capacity. In-process: `polymarket_archive_partition_miss_total`, `polymarket_archive_insert_rate_total`.

## 5. Planes check

Confirm docs/config offer no place/cancel/order paths (`tests/test_archive_no_execution_surface.py`). Reserved future consumer is `NoOpFutureConsumer` only.
