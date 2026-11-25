# G-044–G-046 verification receipt (Phase A1)

**Recorded**: 2026-11-25  
**Host**: local macOS Docker Compose (Postgres 15 + Redis 7)  
**Nature**: Disposable-Postgres + static/services gates. Operator burn-in database (`polymarket_tracker`) was **not** upgraded or downgraded by these gates.

## Scope closed

| Gap | Claim proven here |
| --- | --- |
| G-044 | Forward-only outcome repair + post-cutover KPI wiring; non-blocking insert; health isolation; disposable A1 schema cycle |
| G-045 | Versioned `markets` append/snapshot + Alembic upgrade/downgrade creating `markets` (+ knowability tables) |
| G-046 | Override→series→template(off)→optional Decisions lookup; no trades knowability rewrite; services evidence. **Featuring backfill on regime upgrade remains Phase B** (not claimed closed here) |

## Commands and results

### Focused unit suite (incl. disposable migration)

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
  tests/ingestor/test_archive_dry_run_metadata.py \
  tests/test_archive_no_execution_surface.py \
  -q
```

**Result**: **45 passed**, 0 skipped (migration exercised under `RUN_SERVICE_TESTS=1`).

Standalone migration target also passed earlier in the same session:

`tests/storage/test_markets_knowability_schema.py::test_markets_knowability_migration_upgrade_and_downgrade` → **passed** (creates/drops sibling DB; asserts A1 tables + `repair_enabled_at`).

### Static profile

```bash
uv run python scripts/verify.py --profile static
```

**Result**: **passed** (lock, format, lint, mypy, pyright, vulture, complexipy ≤5, C901 ≤10).

### Services profile (disposable only)

```bash
uv run --env-file .env python scripts/verify.py --profile services
```

**Result**: **passed**

| Gate | Evidence |
| --- | --- |
| services / probe | `[PASS] runtime-probe` |
| redis-contract | 52 passed (real Redis + disposable Postgres journeys) |
| migrations | temporary_database `pit_verify_66580d29a13644e0b2116478d8ba3e92`; migration_states `['006_research_trade_archive_a1', '005_research_trade_archive_a0', '006_research_trade_archive_a1']`; `async_query_succeeded: True`; `cleanup_succeeded: True` |

Alembic head exercised: `006_research_trade_archive_a1`.

## Explicit non-claims

- Live burn-in cutover (`ARCHIVE_OUTCOME_REPAIR_ENABLED=true` against operator tape) was **not** performed in this receipt.
- Template matching remains **disabled** (`knowability.templates.v1` reserved).
- Phase B featuring backfill and Phase C labels are out of scope.
