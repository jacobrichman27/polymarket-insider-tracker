# Implementation Plan: Research Trade Archive (Phase A0)

**Branch**: `005-research-trade-archive` | **Date**: 2026-11-18 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/005-research-trade-archive/spec.md` (clarified 2026-11-18), amended slice 001 observation-boundary / status contracts, amended slice 003 health-endpoints / pipeline-lifecycle, root [`Data.md`](../../Data.md), and [`docs/research-archive-roadmap.md`](../../docs/research-archive-roadmap.md).

## Summary

Land Phase A0 of the research trade archive as an **opt-in** (`ARCHIVE_ENABLED` default **false**) consumer on the existing `TradePoller`: ordered Archive → Monitor fan-out of full `TradeObservation` (Monitor may stay `TradeEvent`-only), idempotent partitioned Postgres `trades` inserts with Core hot raw, durable `ingest_gap_events` for ingest-loss copy and write-failure recovery under policy **(a)** (retain only after durable insert; checkpoint stall), once-set `archive_start_at`, and a `trade_archive` readiness component when enabled. No versioned markets, fingerprints, stored `data_complete`, featuring, labels, or execution.

## Technical Context

**Language/Version**: CPython 3.11–3.13; syntax baseline 3.11 (unchanged).

**Primary Dependencies**: Existing stack — SQLAlchemy / async Postgres driver, Alembic, Redis (`redis.asyncio`), pydantic-settings, prometheus-client, httpx. No new dependency required for A0. Test doubles: fakeredis, httpx.MockTransport, disposable Postgres/SQLite engines; `unittest.mock` prohibited.

**Storage**: PostgreSQL adds partitioned `trades`, `ingest_gap_events`, and `archive_collector_state`. Redis remains the slice-001 complete-through / identity / loss-events operational buffer; A0 mirrors losses durably. No SQLite-as-prod-tape claim.

**Testing**: pytest / pytest-asyncio; extend `tests/ingestor/_poller_harness.py` and fakes; Real Redis contract scenarios if new Redis ops appear; services profile for Alembic upgrade/downgrade on real Postgres; health SLO tests with controllable clock.

**Target Platform**: Linux (Ubuntu 24.04 x86_64 blocking reference) and Apple Silicon macOS, unchanged.

**Project Type**: Single Python package / long-running CLI monitoring service with optional research tape.

**Performance Goals**: Preserve 5s poll cadence; Archive insert on hot path must not introduce blocking Gamma/Jev; tape SLOs per 003 amendment (30s/60s/5min); provisional capacity assumes 5×10⁵–2×10⁶ rows/day with raw-on sizing.

**Constraints**: Research/monitoring only; dry-run must not deliver or poison delivery dedup; assessment persist must not block alerts; Complexipy ≤5; Ruff C901 ≤10; strict mypy/Pyright; Vulture default; Black 100; Relentless enrolled controls only grow; no suppressions/baselines.

**Scale/Scope**: One feature directory; touch poller delivery, config, storage models/repos, Alembic revision, health wiring, pipeline assembly, docs (`.env.example`, README migration note); own gaps G-035–G-043 through implement/converge. Out of scope: A1–D and execution.

## Constitution Check

*GATE: Passed before Phase 0 research; re-checked after Phase 1 design.*

| Rule | Evidence | Result |
|---|---|---|
| I. Research and monitoring only | No order placement; reserved bus slot is interface-only; FR-018/FR-021. | Pass |
| II. Truthful, source-grounded contracts | Reuses documented public trades poll; archive is explicit config; raw/identity semantics match Data.md + 001. | Pass |
| III. End-to-end evidence | Quickstart + fan-out/idempotency/abandon/health scenarios required; no mock framework. | Pass |
| IV. Safe effects and durable records | Assessment≠tape-down; dry-run unchanged for delivery; tape durability separate from alerts. | Pass |
| V. Compatibility / reproducibility | `ARCHIVE_ENABLED` default false; monitor-only path preserved; Alembic downgrade required; public APIs migrate via adapter. | Pass |
| Spec Kit workflow | Explicit `SPECIFY_FEATURE_DIRECTORY`; specify→clarify→plan; reviewer checklist later unchecked. | Pass |

No constitution exception is requested.

### Post–Phase 1 re-check

Design artifacts (`research.md`, `data-model.md`, `contracts/*`, `quickstart.md`) stay inside A0 bounds, name 001/003 as owners of boundary/health, and do not introduce execution modules. Gate remains **Pass**.

## Project Structure

### Documentation (this feature)

```text
specs/005-research-trade-archive/
├── spec.md
├── plan.md                 # this file
├── research.md             # Phase 0
├── data-model.md           # Phase 1
├── quickstart.md           # Phase 1
├── contracts/
│   ├── observation-fanout.md
│   ├── archive-persistence.md
│   └── archive-config-and-health.md
├── checklists/
│   └── requirements.md     # author-owned
└── tasks.md                # created by $speckit-tasks (not this command)
```

### Source Code (repository root)

```text
src/polymarket_insider_tracker/
├── config.py                          # ArchiveSettings (ARCHIVE_*)
├── pipeline.py / pipeline_components.py  # wire fan-out when enabled
├── ingestor/
│   ├── trade_poller.py                # delivery driver: policy (a) vs monitor-only
│   ├── trade_rows.py                  # TradeObservation + raw capture
│   ├── observation_boundary.py        # stall/advance rules when archive-credited
│   ├── health.py / readiness.py       # register trade_archive checker
│   └── archive/                       # NEW: writer, gap ledger, collector state, owed metrics
│       ├── writer.py
│       ├── gap_ledger.py
│       └── state.py
└── storage/
    ├── models.py                      # TradeModel, IngestGapEventModel, ArchiveCollectorState
    └── repos.py                       # idempotent insert + gap upserts
alembic/versions/
└── rev_*_research_trade_archive_a0.py # partitioned trades + gaps + state; downgrade path
tests/
├── ingestor/                          # fan-out, stall, crash, abandon
├── storage/                           # idempotent insert, partitions if applicable
├── integration/                       # postgres migration + redis parity as needed
└── fakes/                             # injectable archive writer / failing session
```

**Structure Decision:** Stay in the existing single package. Add a focused `ingestor/archive/` package for the writer and ledger rather than a second service process. Reuse `TradePoller` and Redis boundary; do not add a parallel acquisition daemon.

## Complexity Tracking

> No constitution violations requiring justification.

## Implementation approach (for tasks decomposition)

1. **Schema first** — Alembic A0 tables/partitions/indexes; models/repos; collector state set-once.
2. **Observation raw capture** — Ensure parse path retains provider payload onto `TradeObservation`.
3. **Archive writer** — Idempotent insert + metrics + owed tracking.
4. **Gap ledger** — Mirror Redis ingest losses; write_failure lifecycle.
5. **Poller fan-out** — Dual mode delivery; checkpoint stall; abandon path.
6. **Pipeline/config** — `ARCHIVE_*`; wire Archive+Monitor when enabled.
7. **Health** — `trade_archive` component per 003 SLOs.
8. **Docs/tests/verify** — `.env.example`, README migration note, quickstart scenarios, gap-register evidence.

## Provisional capacity (acceptance)

| Topic | A0 plan default |
| --- | --- |
| Partition grain | Daily UTC on `trade_ts`; pre-create ≥7 days; alarm if missing |
| Indexes | PK `(trade_ts, observation_id)`; `(condition_id, trade_ts)`; `(proxy_wallet, trade_ts)`; `(transaction_hash, trade_ts)` |
| Hot / interim | 14d hot detail incl. raw; ~90d on primary then detach |
| Growth | 5×10⁵–2×10⁶ rows/day; ~2.5–10 KiB/row raw-on; index 0.5–1.5×; safety ≥2 |
| Alarms | **In-process:** missing partition / partition-miss signal; insert-rate metric (ops compares to 2× sizing); owed backlog → `trade_archive`. **Ops/host:** disk ≥70% of documented budget (runbook; not an in-process disk poller) |
| Retry backoff | 250 ms → ×2 → cap 5 s while owed and reachable |
| Dry-run | Still inserts to tape when `ARCHIVE_ENABLED`; no real notification delivery |
| Locator columns | Deferred to Phase B (not nullable stubs in A0) |

Revise after 72h metrics; do not ship unbounded “keep forever with no budget.”

## Dependencies / ownership

| Concern | Owner |
| --- | --- |
| Identity, proof, policy (a) retain/stall vocabulary | Slice 001 contracts (amended); 005 implements |
| `/ready` + `trade_archive` SLO table | Slice 003 contracts (amended); 005 wires signals |
| Trades schema, writer, gaps, archive config | Slice 005 |
| Markets / Gamma repair | Slice 006 (A1) |
| Fingerprints / featuring | Slice 007 (B) |

## Gaps owned

G-035, G-036–G-038 (implement), G-039–G-043 — remain **Open** until implement evidence; dispositions update through converge.
