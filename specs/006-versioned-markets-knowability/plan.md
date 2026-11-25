# Implementation Plan: Versioned Markets & Knowability (Phase A1)

**Branch**: `006-versioned-markets-knowability` | **Date**: 2026-11-23 | **Spec**: [spec.md](spec.md)

**Input**: Clarified feature specification (`specs/006-versioned-markets-knowability/spec.md`, clarify session 2026-11-22), Phase A0 (`005-research-trade-archive`) as implemented on `main`, root [`Data.md`](../../Data.md) Outcome-repair / Knowability / Canonical tables, and [`docs/research-archive-roadmap.md`](../../docs/research-archive-roadmap.md).

## Summary

Land Phase **A1** as async research metadata on top of the A0 trades tape: append-on-change versioned `markets` (and knowability caches) when `ARCHIVE_ENABLED`, plus **forward-only** outcome repair gated by a **separate** explicit setting (`ARCHIVE_OUTCOME_REPAIR_ENABLED`, default **false**) that records a durable cutover time. Repair and classification MUST NEVER block observation emission or idempotent trades insert. Model-on-miss is **on when credentials exist** (force-off supported), with a hard daily call budget (default **10 000**) and circuit-breaker. No featuring, fingerprints, labels, retention automation, or execution.

## Technical Context

**Language/Version**: CPython 3.11–3.13; syntax baseline 3.11 (unchanged).

**Primary Dependencies**: Existing stack — SQLAlchemy async Postgres, Alembic, Redis, pydantic-settings, prometheus-client, httpx (Gamma). Knowability model-on-miss default adapter: **OpenAI Decisions API** (`gpt-6-luna`); effectively on when credentials are configured (force-off + daily budget). A1 acceptance MUST NOT require a live model vendor. Test doubles: httpx.MockTransport / lightweight fakes; `unittest.mock` prohibited.

**Storage**: PostgreSQL adds versioned `markets`, knowability series/template cache tables (and policy/cutover state). Updates `trades` repaired outcome columns **only** for post-cutover rows when repair is enabled. Redis remains A0 boundary; A1 does not redefine it.

**Testing**: pytest / pytest-asyncio; disposable Postgres for migrations and snapshot-join tests; injectable Gamma transport; clock control for repair-lag KPI; prove insert path unaffected under slow/failing repair.

**Target Platform**: Linux (Ubuntu 24.04 x86_64 blocking) and Apple Silicon macOS, unchanged.

**Project Type**: Single Python package / long-running CLI monitoring + research archive service.

**Performance Goals**: Preserve 5s poll and A0 tape SLOs; repair/classification on async workers; provisional repair attempt lag **5 minutes**; unrepaired thin-row ceiling **≤5%** over trailing day (post-cutover population only).

**Constraints**: Research/monitoring only; dry-run still writes tape + A1 durable metadata when archive on, without Discord/Telegram; constitution IV intact; Complexipy ≤5; C901 ≤10; strict mypy/Pyright; Vulture; Black 100; no suppressions.

**Scale/Scope**: One feature directory; extend `ArchiveSettings`, `ingestor/` (markets + repair workers), storage models/repos, Alembic revision, health/metrics for repair KPI (not redefining `trade_archive` down as “repair lagging”). Own new A1 gap rows through converge. Out of scope: Phase B–D and execution.

## Constitution Check

*GATE: Passed before Phase 0 research; re-checked after Phase 1 design.*

| Rule | Evidence | Result |
|---|---|---|
| I. Research and monitoring only | No order placement; FR-016; no execution modules. | Pass |
| II. Truthful, source-grounded contracts | Gamma as public market-metadata source already in product; repair never invents outcomes; settings defaults documented. | Pass |
| III. End-to-end evidence | Quickstart + repair/markets/lookup/non-blocking scenarios; no mock framework. | Pass |
| IV. Safe effects and durable records | Repair failure ≠ alert block; dry-run delivery rules preserved; tape durability unchanged. | Pass |
| V. Compatibility / reproducibility | `ARCHIVE_ENABLED` default false unchanged; repair default false; Alembic downgrade required; A0 insert key preserved. | Pass |
| Spec Kit workflow | Explicit `SPECIFY_FEATURE_DIRECTORY=specs/006-versioned-markets-knowability`. | Pass |

No constitution exception is requested.

### Post–Phase 1 re-check

Design artifacts stay inside A1 bounds, keep 001/003/005 ownership of boundary/tape/health, and do not introduce featuring or execution. Gate remains **Pass**.

## Project Structure

### Documentation (this feature)

```text
specs/006-versioned-markets-knowability/
├── spec.md
├── plan.md                 # this file
├── research.md             # Phase 0
├── data-model.md           # Phase 1
├── quickstart.md           # Phase 1
├── contracts/
│   ├── outcome-repair.md
│   ├── versioned-markets.md
│   ├── knowability.md
│   ├── knowability-templates.md
│   └── a1-config-and-health.md
├── checklists/
│   └── requirements.md
└── tasks.md                # created by $speckit-tasks (not this command)
```

### Source Code (repository root)

```text
src/polymarket_insider_tracker/
├── config.py                    # ArchiveSettings: OUTCOME_REPAIR_*, KNOWABILITY_MODEL_ENABLED, MAX_CALLS_PER_DAY, lag/ceiling
├── pipeline.py / components     # start async markets + repair workers when archive on
├── ingestor/
│   ├── gamma_client.py          # reuse for market metadata / token→outcome (non-blocking callers)
│   └── archive/                 # extend A0 package
│       ├── markets.py           # append-on-change markets writer + snapshot read
│       ├── knowability.py       # override → series → template → optional model
│       ├── outcome_repair.py    # forward-only repair worker
│       ├── repair_kpi.py        # post-cutover rates / metrics
│       └── state.py             # repair_enabled_at cutover (extend collector state)
└── storage/
    ├── models.py                # MarketVersion, knowability caches, cutover fields
    └── repos.py                 # append version; update repaired columns post-cutover only
alembic/versions/
└── rev_*_research_trade_archive_a1.py
tests/
├── ingestor/                    # repair forward-only, non-blocking insert, lookup order, KPI
├── storage/                     # markets append + snapshot join
└── integration/                 # migration upgrade/downgrade on disposable Postgres
```

**Structure Decision:** Extend `ingestor/archive/` rather than a second process. Markets/knowability warm when archive is on; repair worker only when `ARCHIVE_OUTCOME_REPAIR_ENABLED`. No parallel acquisition feed.

## Complexity Tracking

No unjustified new complexity. Optional model adapter is credential-gated with force-off and a hard daily budget. Async workers are required to satisfy the non-blocking insert gate.

## Implementation Phases (for tasks.md)

1. Schema + repos: `markets`, caches, cutover; migration downgrade.
2. Markets writer (archive-on) + snapshot join API.
3. Outcome repair worker (repair-on, forward-only) + never-invent + KPI metrics.
4. Knowability lookup + policy versioning; model adapter (credential-gated, budget + circuit-breaker).
5. Config/docs/health signals; prove A0 insert path unchanged under injected Gamma slowness.
6. Gap-register + verify gates (without pointing tests at a live 72h operator DB).
