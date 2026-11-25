# Quickstart: Versioned Markets & Knowability (Phase A1)

**Feature**: `specs/006-versioned-markets-knowability`  
**Date**: 2026-11-23  
**Purpose**: Validation scenarios after implement. Not a substitute for `tasks.md`.

**Ops note:** Do not point destructive tests or migrations at an active operator burn-in database without consent. Use disposable Postgres for gates.

## Prerequisites

```bash
uv sync --locked --all-extras --python 3.13   # via mise uv 0.11.x
cp .env.example .env
docker compose up -d postgres redis
# Disposable DB only — do not point at a live burn-in DATABASE_URL without consent
uv run alembic upgrade head   # includes 006_research_trade_archive_a1
```

## 1. Archive on, repair off (metadata warm-up)

```bash
ARCHIVE_ENABLED=true
ARCHIVE_OUTCOME_REPAIR_ENABLED=false
```

**Expect:** trades insert as A0; markets versions MAY appear; trades stay `not_attempted` / unrepaired; no post-cutover repair KPI population; `/ready` still uses A0 `trade_archive` rules.

## 2. Enable repair cutover

```bash
ARCHIVE_OUTCOME_REPAIR_ENABLED=true
```

**Expect:** durable `repair_enabled_at` set once; new thin fills progress to `ok` / `unrepaired` / `not_needed` without blocking insert; pre-cutover rows not required to change.

## 3. Focused verification (post-implement paths)

```bash
RUN_SERVICE_TESTS=1 uv run --env-file .env pytest \
  tests/storage/test_markets_versioning.py \
  tests/storage/test_markets_knowability_schema.py \
  tests/ingestor/test_outcome_repair_forward_only.py \
  tests/ingestor/test_outcome_repair_nonblocking.py \
  tests/ingestor/test_outcome_repair_api_gamma_disagree.py \
  tests/ingestor/test_outcome_repair_kpi.py \
  tests/ingestor/test_outcome_repair_kpi_wiring.py \
  tests/ingestor/test_outcome_repair_health_isolation.py \
  tests/ingestor/test_knowability_lookup_order.py \
  tests/ingestor/test_knowability_templates.py \
  tests/ingestor/test_knowability_model_guardrails.py \
  tests/ingestor/test_knowability_no_trades_rewrite.py \
  tests/ingestor/test_knowability_regimes_admit.py \
  tests/ingestor/test_markets_writer_archive_on.py \
  tests/ingestor/test_gamma_market_shapes.py \
  tests/ingestor/test_market_warm_dedupe.py \
  tests/ingestor/test_decisions_client.py \
  -q
```

Receipt: [`evidence/g044-g046-verification.md`](evidence/g044-g046-verification.md).

Coverage includes: append-on-change + snapshot join; forward-only population; never-invent; insert succeeds under slow Gamma; lookup override→series→template→(optional model); KPI scoped post-cutover; model on when credentials exist; daily budget / circuit leave `unknown` without stalling insert.

## 4. Gates

```bash
uv run python scripts/verify.py --profile static
uv run --env-file .env python scripts/verify.py --profile services
```

## 5. Planes check

No place/cancel/order paths; repair degraded ≠ trading advice.
