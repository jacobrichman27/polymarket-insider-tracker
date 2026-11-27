# Quickstart: Featured Enrichment

**Feature**: `specs/007-featured-enrichment`  
**Date**: 2026-11-25  
**Purpose**: Validation scenarios after implement. Not a substitute for `tasks.md`.

**Ops note:** Do not point destructive tests or migrations at an active operator burn-in database without consent. Use disposable Postgres for gates.

## Prerequisites

```bash
# uv 0.11.x via mise — not Homebrew 0.12
eval "$(~/.local/bin/mise activate zsh)"
uv sync --locked --all-extras --python 3.13
cp .env.example .env
docker compose up -d postgres redis
# Disposable DB only
uv run --env-file .env alembic upgrade head   # includes 008_featured_enrichment
```

Activate Spec Kit commands with:

```bash
SPECIFY_FEATURE_DIRECTORY=specs/007-featured-enrichment
```

## 1. Archive on, featuring off

```bash
ARCHIVE_ENABLED=true
ARCHIVE_FEATURING_ENABLED=false
```

**Expect:** trades tape + markets/knowability behavior unchanged; no featuring enqueue; `/ready` tape rules unchanged.

## 2. Enable featuring

```bash
ARCHIVE_FEATURING_ENABLED=true
# cutoff default 5000 unless overridden; hot backfill uses ARCHIVE_HOT_WINDOW_DAYS
```

**Expect:** Eligible fills (`private_edge_possible` + notional) enqueue enrichment asynchronously; inserts continue under enrichment backlog; `unknown` / `no_private_edge` skip priority enrichment (except classifier-control sample).

## 3. Focused verification (post-implement paths)

```bash
uv run pytest \
  tests/ingestor/test_featuring_gate.py \
  tests/ingestor/test_featuring_config_gate.py \
  tests/ingestor/test_featuring_nonblocking.py \
  tests/ingestor/test_enrichment_arms.py \
  tests/ingestor/test_enrichment_budget_degrade.py \
  tests/ingestor/test_featuring_regime_upgrade_backfill.py \
  tests/ingestor/test_featuring_backfill_exclusions.py \
  tests/ingestor/test_fingerprint_version.py \
  tests/ingestor/test_order_as_of_features.py \
  tests/ingestor/test_signed_flow_kpi.py \
  tests/ingestor/test_wallet_hydrate.py \
  tests/storage/test_featured_enrichment_schema.py \
  tests/test_archive_no_execution_surface.py \
  -q
```


## 4. Prefer full gates

```bash
uv run python scripts/verify.py --profile static
uv run --env-file .env python scripts/verify.py --profile services
```

## 5. Planes check

Confirm docs/config offer no place/cancel/order paths. Enrichment lag must not alone fail `trade_archive` readiness.
