# Implementation Plan: Featured Enrichment (Phase B)

**Branch**: `007-featured-enrichment` | **Date**: 2026-11-25 | **Spec**: [spec.md](spec.md)

**Input**: Clarified feature specification (`specs/007-featured-enrichment/spec.md`, clarifications 2026-11-25), Phase A0 (`005`) + A1 (`006`) on `main`, root [`Data.md`](../../Data.md) Featuring / Enrichment / fingerprint / order-as-of / wallet-history locks, and [`docs/research-archive-roadmap.md`](../../docs/research-archive-roadmap.md). Gaps **G-047–G-051**.

## Summary

Land Phase **B** as the **enrichment platform** on top of the admitted trades tape: evaluate the locked featuring gate (`private_edge_possible` + **$5k** provisional notional cutoff), enqueue enrichment without blocking insert, attempt arms in locked order under versioned caps with per-arm statuses, reuse shared arms by natural grain (FR-017 hybrid), hot-window featuring backfill on regime upgrade, lock `fingerprint_version` + `order_as_of_contract`, publish signed-flow KPI before overweighting λ, and keep lifetime hydrate vs archive wallet stories stratified by `wallet_hydrate_status`. Optional `trade_features` **grain/schema** for featured rows only (FR-013 MAY)—**not** Data.md §§1–6 Core/Useful catalog acceptance (owned by proposed B.1 `010-featured-core-features` / B.2 `011-featured-useful-features`; G-052/G-053). No labels (C), retention automation (D), or execution.

## Technical Context

**Language/Version**: CPython 3.11–3.13; syntax baseline 3.11 (unchanged).

**Primary Dependencies**: Existing stack — SQLAlchemy async Postgres, Alembic, Redis, pydantic-settings, prometheus-client, httpx (Gamma / Data API). Polygon JSON-RPC for receipt + Transfer-log arms (existing profiling RPC settings). Optional Dune sync remains scheduled/bulk (not per-fill). Test doubles: httpx.MockTransport, lightweight RPC fakes; `unittest.mock` prohibited.

**Storage**: PostgreSQL extends `trades` with enrichment/fingerprint/locator columns as needed; adds optional `trade_features`; versioned `wallets` / `proxy_funding` (and related hydrate/funding status); featuring/enrichment queue or durable work-item state; version stamps (`featuring_config_version`, `enrichment_budget_version`, `fingerprint_version`, `feature_version`). Redis may hold ephemeral queue leases; durable completeness stays in Postgres. A0/A1 schemas unchanged in semantics (A0 insert key; A1 markets join for regime).

**Testing**: pytest / pytest-asyncio; disposable Postgres for migrations; injectable Gamma/RPC/Data-API transports; clock control for hot-window / budget; prove insert path unaffected under slow enrichment; fingerprint and order-as-of contract tests; signed-flow KPI fixtures; hydrate status stratification.

**Target Platform**: Linux (Ubuntu 24.04 x86_64 blocking) and Apple Silicon macOS, unchanged.

**Project Type**: Single Python package / long-running CLI monitoring + research archive service.

**Performance Goals**: Preserve 5s poll and A0 tape SLOs; featuring/enrichment on async workers only. Provisional enrichment caps (revise after ops data): ~60s wall per attempt, ~8 Polygon RPCs, ~10 hydrate pages or ~15s. Featuring must not starve acquisition (lesson from A0 laptop burn-in).

**Constraints**: Research/monitoring only; dry-run may write enrichment/features when archive+featuring on, without Discord/Telegram; constitution IV intact; Complexipy ≤5; C901 ≤10; strict mypy/Pyright; Vulture; Black 100; no suppressions. `unknown` featuring stays off unless versioned policy bump. Enrichment MUST NOT redefine `trade_archive` down solely because enrichment is lagged (tape SLOs remain insert/owed based).

**Scale/Scope**: One feature directory; extend `ArchiveSettings`, `ingestor/archive/` workers, storage models/repos, Alembic revision(s), metrics/KPI signals. Own G-047–G-051 through converge. Out of scope: Phase C–D, execution, wash-adjusted Core promotion, silent featuring of `unknown`.

## Constitution Check

*GATE: Passed before Phase 0 research; re-checked after Phase 1 design.*

| Rule | Evidence | Result |
|---|---|---|
| I. Research and monitoring only | FR-015; no order placement; no execution modules. | Pass |
| II. Truthful, source-grounded contracts | Caps/cutoff versioned; fingerprint/order-as-of/signed-flow honesty gates; statuses required. | Pass |
| III. End-to-end evidence | Quickstart + gate/budget/backfill/fingerprint/KPI/hydrate scenarios; no mock framework. | Pass |
| IV. Safe effects and durable records | Dry-run delivery rules; enrichment failure ≠ alert block; assessment persist isolation preserved. | Pass |
| V. Compatibility / reproducibility | A0 insert key + A1 markets join preserved; featuring default off or gated behind explicit settings; Alembic downgrade required. | Pass |
| Spec Kit workflow | Explicit `SPECIFY_FEATURE_DIRECTORY=specs/007-featured-enrichment`. | Pass |

No constitution exception is requested.

### Post–Phase 1 re-check

Design artifacts stay inside B bounds, keep 001/003/005/006 ownership of boundary/tape/health/markets, and do not introduce labels or execution. Gate remains **Pass**.

## Project Structure

### Documentation (this feature)

```text
specs/007-featured-enrichment/
├── spec.md
├── plan.md                 # this file
├── research.md             # Phase 0
├── data-model.md           # Phase 1
├── quickstart.md           # Phase 1
├── contracts/
│   ├── featuring-gate.md
│   ├── enrichment-budget.md
│   ├── fingerprint-and-order.md
│   ├── signed-flow-kpi.md
│   ├── wallet-history.md
│   └── b-config-and-health.md
├── checklists/
│   ├── requirements.md
│   └── b-featured-enrichment.md   # reviewer-owned; agents leave [x] unchecked
└── tasks.md
```

### Source Code (repository root)

```text
src/polymarket_insider_tracker/
├── config.py                    # ArchiveSettings: FEATURING_*, ENRICHMENT_* budgets/versions
├── pipeline.py / components     # start async featuring/enrichment workers when archive on
├── ingestor/
│   ├── gamma_client.py          # reuse (non-blocking)
│   ├── clob_client.py / RPC     # receipt + Transfer-log via existing Polygon settings
│   └── archive/                 # extend A0/A1 package
│       ├── featuring.py         # gate eval + enqueue + regime-upgrade backfill
│       ├── enrichment.py        # arm orchestration, budgets, statuses
│       ├── shared_arms.py       # shared-arm reuse + tape pair-assist
│       ├── fingerprint.py       # strong/weak + fingerprint_version
│       ├── signed_flow_kpi.py   # disagreement cohort metrics
│       ├── wallet_hydrate.py    # lifetime hydrate arm + wallets versions
│       ├── funding_sync.py      # proxy_funding writers (Dune schedule + Transfer top-up)
│       └── trade_features.py    # optional snapshot writer
└── storage/
    ├── models.py                # trade_features, wallets, proxy_funding, work items, columns
    └── repos.py                 # enqueue, status updates, snapshot reads
alembic/versions/
└── rev_*_featured_enrichment.py
tests/
├── ingestor/                    # gate, budget degrade, backfill, fingerprint, KPI, hydrate
├── storage/                     # schema + rematerialize joins
└── integration/                 # disposable migration upgrade/downgrade
```

**Structure Decision:** Extend `ingestor/archive/` with async workers (same process). No second acquisition feed. Featuring/enrichment never on the Archive insert hot path.

## Complexity Tracking

No unjustified new complexity. Async workers + budgets are required for non-blocking insert and Partial-arm honesty. FR-017 hybrid reuse reduces duplicate RPC cost versus naive double featuring.

## Implementation Phases (for tasks.md)

1. Schema + repos: enrichment columns, `trade_features`, `wallets` / `proxy_funding`, work-item/queue state; migration downgrade.
2. Featuring gate + config versions; classifier-control sample hook.
3. Enrichment orchestrator (arm order, caps, statuses, FR-017 reuse).
4. Regime-upgrade hot backfill enqueue (consume A1 markets upgrades).
5. Fingerprint + order-as-of materialization contracts; signed-flow KPI.
6. Wallet hydrate + funding arms; stratification fields.
7. Optional `trade_features` writer; metrics/docs/health isolation; prove insert non-blocking.
8. Gap-register evidence + verify gates (disposable DB; do not harm live burn-in).
