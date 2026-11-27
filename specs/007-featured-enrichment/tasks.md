# Tasks: Featured Enrichment (Phase B)

**Input**: Design documents from `specs/007-featured-enrichment/`  
**Prerequisites**: `spec.md` (clarifications 2026-11-25 locked), `plan.md`, `research.md`, `data-model.md`, `contracts/*.md`, `quickstart.md`, reviewer-owned `checklists/b-featured-enrichment.md` (markers owned by the repository owner; agents leave unchecked). A0 (`005`) + A1 (`006`) on `main`.  
**Gaps**: G-047–G-051 Open until proven — update `specs/audit/gap-register.md` with evidence at polish, do not rewrite earlier dispositions.  
**Analyze remediations (2026-11-25)**: C1/C3 folded into T023–T024/T026 + `contracts/featuring-gate.md`; C2 folded into T050. Owner checklist `b-featured-enrichment.md` completed 2026-11-25 (requirements quality only; T001 still gates implement).

**Tests**: Every behavior change begins with a failing test where practical. `unittest.mock` is prohibited; use working fakes, disposable Postgres, httpx / RPC transport fakes, and real value objects per `specs/002-reproducible-runtime/contracts/test-quality.md`. Do **not** point destructive migrations/tests at a live operator burn-in `DATABASE_URL` without consent.

**Ops note**: Featuring/enrichment MUST stay off the Archive insert / poller hot path (US1/US7; Research Decision 2). Enrichment lag MUST NOT alone mark `trade_archive` down (Decision 11). Classifier-control sample provisional rate **0.1%** of featuring-rejected `no_private_edge` (min 1 / max configurable; Decision 9).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no incomplete dependencies)
- **[Story]**: Maps to `US1`–`US7` from `spec.md`

---

## Phase 0: Human Validation Gate

- [x] T001 Record repository-owner human validation authorizing `$speckit-implement` for slice `007-featured-enrichment` in `specs/007-featured-enrichment/tasks.md` (checklist `b-featured-enrichment.md` markers remain owner-owned) [Constitution §Development Workflow 3–4]
  - Validated 2026-11-25 by repository owner: “go ahead” (authorize implement after analyze remediations C1/C2; checklist `b-featured-enrichment.md` already completed).

---

## Phase 1: Setup (Config + Package Surface)

**Purpose**: B settings and module skeleton without changing runtime behavior yet

- [x] T002 Extend `ArchiveSettings` in `src/polymarket_insider_tracker/config.py` with `ARCHIVE_FEATURING_ENABLED` (default `false`; requires `ARCHIVE_ENABLED`), `ARCHIVE_FEATURING_CONFIG_VERSION`, notional cutoff default `5000`, `ARCHIVE_FEATURING_UNKNOWN_OPT_IN` (default `false`), classifier-control sample rate default `0.001`, `ARCHIVE_ENRICHMENT_BUDGET_VERSION`, provisional wall/RPC/hydrate caps (~60s / ~8 RPCs / ~10 pages or ~15s), plus fingerprint/feature version settings; document in `.env.example` (no secrets) [FR-001, FR-002, FR-015; Research Decisions 3/9/10; Contract §b-config-and-health]
- [x] T003 [P] Add failing config/summary tests for featuring defaults (off), archive-required gate, redaction, and version fields in `tests/test_config.py` [Contract §b-config-and-health]
- [x] T004 Create B modules under `src/polymarket_insider_tracker/ingestor/archive/` per `plan.md` (`featuring.py`, `enrichment.py`, `fingerprint.py`, `signed_flow_kpi.py`, `wallet_hydrate.py`, `funding_sync.py`, `trade_features.py`) without wiring workers yet

**Checkpoint**: Config exists; runtime still A0/A1-only behavior

---

## Phase 2: Foundational (Schema + Work Queue)

**Purpose**: Blocking storage for all stories

**⚠️ CRITICAL**: No user-story workers until this phase completes

- [x] T005 [P] Write failing migration/schema tests for enrichment/fingerprint columns on `trades`, optional `trade_features`, versioned `wallets` / `proxy_funding`, and enrichment work-item table (upgrade + downgrade on disposable Postgres) in `tests/storage/test_featured_enrichment_schema.py` [G-047–G-051, Data Model]
- [x] T006 Implement Alembic revision `alembic/versions/rev_*_featured_enrichment.py` with downgrade path per `data-model.md` [FR-006, FR-013, FR-014]
- [x] T007 [P] Add SQLAlchemy models in `src/polymarket_insider_tracker/storage/models.py` for work items, `trade_features`, `wallets`, `proxy_funding`, and trades enrichment columns [Data Model]
- [x] T008 Implement repository helpers in `src/polymarket_insider_tracker/storage/repos.py` for enqueue/claim/complete/abandon work items, arm-status updates, feature snapshot insert (immutable `live_as_of`), and wallet/funding rematerialize reads (`known_at` ≤ `trade_ts` / event-time before `trade_ts`) [FR-006, FR-010, FR-014]

**Checkpoint**: Schema + repos ready; no worker wiring

---

## Phase 3: User Story 1 — Featuring Gate (Priority: P1) 🎯 MVP

**Goal**: Evaluate locked gate (`private_edge_possible` + ≥$5k), enqueue priority enrichment without blocking insert; `unknown` / `no_private_edge` stay unfeatured by default except seeded classifier-control sample

**Independent Test**: Fixture fills across regimes and notional sides of the cutoff; verify enqueue set; insert continues under slow featuring

### Tests

- [x] T009 [P] [US1] Write failing gate eligibility tests (cutoff, regimes, unknown opt-in off, classifier-control seed bounds) in `tests/ingestor/test_featuring_gate.py` [FR-001, FR-002, SC-001; Contract §featuring-gate]
- [x] T010 [P] [US1] Write failing non-blocking insert under slow/disabled featuring in `tests/ingestor/test_featuring_nonblocking.py` [FR-003, SC-008]
- [x] T011 [P] [US1] Write failing tests that featuring stays off unless `ARCHIVE_ENABLED` and `ARCHIVE_FEATURING_ENABLED` in `tests/ingestor/test_featuring_config_gate.py` [Decision 10]

### Implementation

- [x] T012 [US1] Implement featuring evaluation + enqueue (insert-time trigger) and classifier-control sample hook in `src/polymarket_insider_tracker/ingestor/archive/featuring.py` [FR-001, FR-002, FR-017 eligibility; Decision 9]
- [x] T013 [US1] Wire featuring worker only when archive on **and** `ARCHIVE_FEATURING_ENABLED=true` in `pipeline.py` / `pipeline_components.py` (async/non-blocking relative to insert) [FR-003]

**Checkpoint**: Gate MVP works; enrichment arms may still be stubs

---

## Phase 4: User Story 2 — Budgeted Enrichment Arms (Priority: P1)

**Goal**: Attempt arms in locked order under versioned caps with per-arm statuses; FR-017 reuse by natural grain; degrade from bottom; never skip markets/Gamma for featured rows

**Independent Test**: Success, cache reuse, budget skip, failure, pending paths; degrade order; Gamma not skipped

### Tests

- [x] T014 [P] [US2] Write failing arm-order + status honesty tests in `tests/ingestor/test_enrichment_arms.py` [FR-004, FR-006, SC-002; Contract §enrichment-budget]
- [x] T015 [P] [US2] Write failing budget degrade-from-bottom tests (hydrate→funding→receipt; markets never skipped) in `tests/ingestor/test_enrichment_budget_degrade.py` [FR-005]
- [x] T016 [P] [US2] Write failing FR-017 reuse + tape pair-assist tests (receipt once per tx/fingerprint; funding/hydrate once per proxy; unfeatured opposite leg gets tape counterparty edge) in `tests/ingestor/test_enrichment_hybrid_reuse.py` [FR-017]

### Implementation

- [x] T017 [US2] Implement enrichment orchestrator (caps, statuses, retry/abandon while hot) in `src/polymarket_insider_tracker/ingestor/archive/enrichment.py` [FR-004–FR-006]
- [x] T018 [P] [US2] Implement markets/Gamma arm status recording (reuse A1 markets / Gamma client; non-blocking) inside enrichment path [FR-004, FR-005]
- [x] T019 [P] [US2] Implement receipt-decode arm via existing Polygon RPC settings in enrichment path (locators, `onchain_direction`, counterparties as available) [FR-004; Data.md]
- [x] T020 [P] [US2] Implement Transfer-log funding miss/top-up arm in `src/polymarket_insider_tracker/ingestor/archive/funding_sync.py` (no per-fill Dune) [FR-004, FR-014]
- [x] T021 [P] [US2] Implement lifetime hydrate arm skeleton (status + budget skip; full stratification completed in US6) in `src/polymarket_insider_tracker/ingestor/archive/wallet_hydrate.py` [FR-004, FR-012]
- [x] T022 [US2] Wire enrichment worker to claim work items when featuring enabled; prove insert does not await enrichment completion [FR-003, SC-008]

**Checkpoint**: Featured fills get honest Partial arms under budget

---

## Phase 5: User Story 3 — Regime-Upgrade Hot Backfill (Priority: P1)

**Goal**: On upgrade to `private_edge_possible`, enqueue hot notional-eligible fills not completed/abandoned for current budget version; never enqueue on `no_private_edge`; no trades knowability rewrite

**Independent Test**: Store hot `unknown` fills; upgrade; verify enqueue; upgrade to `no_private_edge` enqueues zero; left-hot not pretended receipt-enrichable

### Tests

- [x] T023 [P] [US3] Write failing hot-window enqueue-on-upgrade tests in `tests/ingestor/test_featuring_regime_upgrade_backfill.py`, including a clock-controlled case where `trade_ts` is exactly at / just past the configured hot horizon at enqueue decision time (assert not newly receipt-enrichable); pin the A0 hot/retention setting name used for “still hot” [FR-007, SC-003; Contract §featuring-gate; analyze C1/C3]
- [x] T024 [P] [US3] Write failing tests for `no_private_edge` upgrade (no enqueue), left-hot exclusion, and concurrent “leaving hot while enqueue runs” (same clock) so enqueue excludes/no-ops without claiming enrichment for that row in `tests/ingestor/test_featuring_backfill_exclusions.py` [FR-008; analyze C1]
- [x] T025 [P] [US3] Write failing test that B enqueue does not rewrite historical trades knowability columns in `tests/ingestor/test_featuring_no_trades_knowability_rewrite.py` [FR-007; A1 join rule]

### Implementation

- [x] T026 [US3] Implement regime-upgrade observer + hot featured backfill enqueue in `src/polymarket_insider_tracker/ingestor/archive/featuring.py` (consume A1 markets upgrades; B owns worker; hot = still inside configured hot retention window at enqueue decision time) [FR-007–FR-008; Contract §featuring-gate]
- [x] T027 [US3] Wire upgrade-triggered enqueue into pipeline when featuring enabled (still off insert hot path) [FR-003, FR-007]

**Checkpoint**: Async knowability no longer permanently starves early large fills still hot

---

## Phase 6: User Story 4 — Fingerprint & Order-As-Of (Priority: P2)

**Goal**: Version strong vs weak fingerprints; materialize order-dependent fields with `live_as_of` / `fully_enriched`; never overwrite frozen `live_as_of` in place

**Independent Test**: Colliding weak keys vs receipt-strong keys; primary-analysis gate; peer locator arrival requires new feature version

### Tests

- [x] T028 [P] [US4] Write failing strong/weak fingerprint + `fingerprint_version` tests in `tests/ingestor/test_fingerprint_version.py` [FR-009, SC-004; Contract §fingerprint-and-order]
- [x] T029 [P] [US4] Write failing `order_as_of_contract` immutability / rematerialize tests in `tests/ingestor/test_order_as_of_features.py` [FR-010, SC-004]
- [x] T030 [P] [US4] Write failing primary-analysis readiness gate tests (weak not Core until rematerialized; sensitivity label allowed) in `tests/ingestor/test_fingerprint_analysis_gate.py` [FR-009, SC-004]

### Implementation

- [x] T031 [US4] Implement fingerprint computation + version stamps in `src/polymarket_insider_tracker/ingestor/archive/fingerprint.py` [FR-009]
- [x] T032 [US4] Implement optional `trade_features` writer with `order_as_of_contract` and no in-place `live_as_of` overwrite in `src/polymarket_insider_tracker/ingestor/archive/trade_features.py` [FR-010, FR-013] — grain/immutability only; Core/Useful payload catalogs → `010`/`011` (G-052/G-053)
- [x] T033 [US4] Integrate fingerprint + feature materialization into enrichment completion path (featured rows only; no Phase C labels) [FR-013] — provenance snapshot path; full Core materialization is B.1 not this task

**Checkpoint**: Match-once and order-dependent honesty contracts enforceable

---

## Phase 7: User Story 5 — Signed-Flow KPI (Priority: P2)

**Goal**: Convention-signed aggregates use API `side` on fingerprint-deduped canonical leg; publish disagreement KPI before λ/imbalance Core overweighting

**Independent Test**: Cohort with receipt ok/partial; agreement classes countable; primary overweighting gated until KPI published for cohort

### Tests

- [x] T034 [P] [US5] Write failing signed-flow disagreement classification tests in `tests/ingestor/test_signed_flow_kpi.py` [FR-011, SC-005; Contract §signed-flow-kpi]
- [x] T035 [P] [US5] Write failing tests that market-tape signed aggregates use API `side` on convention canonical leg (not arrival-order aggressor claim) in `tests/ingestor/test_signed_flow_convention.py` [FR-011]
- [x] T036 [P] [US5] Write failing gate test that λ/imbalance stay Useful/sensitivity until KPI published for feature/enrichment cohort in `tests/ingestor/test_signed_flow_core_gate.py` [FR-011, SC-005]

### Implementation

- [x] T037 [US5] Implement disagreement KPI signals/metrics in `src/polymarket_insider_tracker/ingestor/archive/signed_flow_kpi.py` (+ prometheus hooks) [FR-011]
- [x] T038 [US5] Register signed-flow KPI as diagnostic/health signal without redefining A0 tape SLOs in `ingestor/health.py` / pipeline wiring [Decision 11; Contract §b-config-and-health]

**Checkpoint**: Operators can see signed-flow honesty before Core overweighting

---

## Phase 8: User Story 6 — Wallet-History Dualism (Priority: P2)

**Goal**: Lifetime hydrate vs archive-path features stay distinct; stratify by `wallet_hydrate_status`; `lifetime_is_first_trade` only on complete empty walk; rematerialize rules for wallets/funding

**Independent Test**: Complete / partial / skipped_budget hydrate; later archive fills; stratification required in analysis contracts

### Tests

- [x] T039 [P] [US6] Write failing hydrate status + `lifetime_is_first_trade` null-unless-complete-empty tests in `tests/ingestor/test_wallet_hydrate.py` [FR-012, SC-006; Contract §wallet-history]
- [x] T040 [P] [US6] Write failing stratification / no silent hybrid tests in `tests/ingestor/test_wallet_history_stratification.py` [FR-012, SC-006]
- [x] T041 [P] [US6] Write failing wallets / proxy_funding rematerialize join tests in `tests/storage/test_wallet_funding_rematerialize.py` [FR-014]

### Implementation

- [x] T042 [US6] Complete lifetime hydrate arm + versioned `wallets` writes in `src/polymarket_insider_tracker/ingestor/archive/wallet_hydrate.py` [FR-012, FR-014]
- [x] T043 [US6] Complete scheduled/bulk Dune + Transfer top-up writers for `proxy_funding` in `src/polymarket_insider_tracker/ingestor/archive/funding_sync.py` (still no per-fill Dune) [FR-014]
- [x] T044 [US6] Ensure enrichment/feature contracts require `wallet_hydrate_status` when hydrate fields are consumed [FR-012, SC-006]

**Checkpoint**: Two wallet stories cannot be silently mixed

---

## Phase 9: User Story 7 — Research-Only Surface (Priority: P3)

**Goal**: No execution surface; dry-run may write enrichment/features without Discord/Telegram; assessment persist failure still non-blocking; enrichment lag ≠ tape down

**Independent Test**: Config/docs/tests; dry-run no delivery; assessment isolation; ready rules unchanged under enrichment backlog

### Tests

- [x] T045 [P] [US7] Extend `tests/test_archive_no_execution_surface.py` (or sibling) so B settings/docs introduce no place/cancel/order surface [FR-015, SC-007]
- [x] T046 [P] [US7] Write failing dry-run + featuring enrichment durable-without-notify tests in `tests/ingestor/test_featuring_dry_run.py` [FR-015, SC-007]
- [x] T047 [P] [US7] Write failing test that enrichment lag/KPI degraded ≠ `trade_archive` down / ready fail in `tests/ingestor/test_enrichment_health_isolation.py` [Decision 11, SC-008]
- [x] T048 [P] [US7] Extend assessment-persist isolation tests so featuring/enrichment enabled still does not block authorized alerts in `tests/ingestor/test_trade_archive_assessment_isolation.py` (or dedicated module) [FR-015]

### Implementation

- [x] T049 [US7] Audit pipeline wiring so featuring/enrichment cannot await on the Archive insert hot path; fix regressions in `pipeline.py` / `trade_poller.py` / archive workers [FR-003, FR-015]
- [x] T050 [US7] Enforce FR-016 wash-adjusted demotion fail-closed: (a) assert docs (`Data.md` / README / B docs) keep wash-adjusted market stats Useful/Partial under the featuring gate until a separate approved gate; (b) if any wash-adjusted aggregate helper already exists under `src/`, add a failing test that primary/Core readiness rejects it until that approval; (c) if no such helper exists, record that honestly in T050 evidence and do **not** invent wash Core promotion code in B [FR-016; analyze C2]

**Checkpoint**: Constitution I/IV hold with B workers present

---

## Phase 10: Polish & Cross-Cutting

- [x] T051 [P] Align `specs/007-featured-enrichment/quickstart.md` with real module/test paths after implement
- [x] T052 [P] Document B flags, cutoff/caps/versions, classifier-control rate, fingerprint/order-as-of, signed-flow KPI gate, and wallet stratification in `README.md` / `.env.example` (no secrets) [FR-015]
- [x] T053 Update `specs/audit/gap-register.md` dispositions for G-047–G-051 with evidence pointers (remain Open until proven; append receipts)
- [x] T054 Update `docs/research-archive-roadmap.md` Phase B status after verification (honest: implemented vs locally verified vs merged)
- [x] T055 Run Spec Kit converge against `007` artifacts; append any remaining work as new tasks rather than rewriting history
- [x] T056 Run required verification on a disposable DB / clean tree: `uv run python scripts/verify.py --profile static` and services profile as applicable; record honest results in slice evidence if claimed
- [x] T057 [P] Run `uv run --locked --group dev python -m quality.verify` before proposing merge; keep `quality/checks.json` enrollments fail-closed

---

## Phase 11: Deferred ops honesty audit (future step — not blocking local implement)

Logged 2026-11-26 in [`evidence/deferred-ops-audit-backlog.md`](./evidence/deferred-ops-audit-backlog.md). Execute after merge (or on a disposable cohort) once receipt decode has a closed vocabulary. Do not close G-047–G-051 from unit tests alone.

- [ ] T058 [P] Keep `evidence/deferred-ops-audit-backlog.md` as the living register (A-001–A-017); append dated evidence links when items are run—do not rewrite history to imply earlier completion
- [ ] T059 Implement closed `onchain_direction` vocabulary + real receipt decode sufficient for A-001 / A-006–A-008 (disposable RPC only; never burn-in DB as scratch)
- [ ] T060 Add disposable-cohort audit export/script covering weak collision (A-003), strong rematerialize (A-004), multi-maker sweep grain (A-005), and disagreement histogram (A-006)
- [ ] T061 Run stratified forensic samples (collision / mint–merge / true_mismatch) and record append-only evidence; publish signed-flow KPI only after A-006 criteria met
- [ ] T062 Revisit G-047–G-051 dispositions with audit receipts; close only when backlog close criteria and main-verified state agree

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 0**: Human validation before implement
- **Phase 1 Setup**: Immediate after T001
- **Phase 2 Foundational**: Blocks all stories
- **Phase 3 US1 (gate)**: MVP after foundational
- **Phase 4 US2 (enrichment)**: After US1 enqueue exists (work items)
- **Phase 5 US3 (backfill)**: After US1 gate + work-item repos; can parallelize with late US2 once enqueue API stable
- **Phase 6 US4 (fingerprint)**: After receipt locators available (US2 receipt arm)
- **Phase 7 US5 (signed-flow)**: After fingerprint + receipt statuses (US2/US4)
- **Phase 8 US6 (wallet)**: Completes hydrate/funding from US2 skeletons
- **Phase 9 US7**: After workers wired (tests can start earlier)
- **Phase 10 Polish**: After desired stories complete

### User Story Dependencies

- **US1**: After Phase 2 — no story deps → **MVP**
- **US2**: After US1 enqueue
- **US3**: After US1 (+ markets regime join from A1)
- **US4**: After US2 receipt arm (locators)
- **US5**: After US4 fingerprint + US2 receipt statuses
- **US6**: After US2 hydrate/funding skeletons
- **US7**: Cross-cutting after wiring

### Parallel Opportunities

- T003 ∥ T004 after T002
- T005 ∥ T007 after plan freeze
- T009 ∥ T010 ∥ T011; T014 ∥ T015 ∥ T016; T023 ∥ T024 ∥ T025
- T018 ∥ T019 ∥ T020 ∥ T021 after T017 skeleton
- T028 ∥ T029 ∥ T030; T034 ∥ T035 ∥ T036; T039 ∥ T040 ∥ T041; T045–T048
- US3 implementation can proceed in parallel with late US2 once featuring enqueue API is stable
- US4–US6 can staff in parallel after US2 receipt/hydrate stubs land

---

## Parallel Example: User Story 1

```bash
# Failing tests together:
Task: "Gate eligibility in tests/ingestor/test_featuring_gate.py"
Task: "Non-blocking insert in tests/ingestor/test_featuring_nonblocking.py"
Task: "Config gate in tests/ingestor/test_featuring_config_gate.py"

# Then implementation:
Task: "featuring.py gate + enqueue"
Task: "Wire featuring worker in pipeline"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 0–2
2. Complete Phase 3: US1 featuring gate + enqueue
3. **STOP and VALIDATE**: Gate selects the right population; insert unaffected
4. Then land US2 arms before claiming Partial enrichment honesty

### Incremental Delivery

1. Setup + Foundational → schema ready  
2. US1 → featuring MVP  
3. US2 → budgeted arms + FR-017  
4. US3 → hot backfill  
5. US4 → fingerprint / order-as-of  
6. US5 → signed-flow KPI  
7. US6 → wallet dualism complete  
8. US7 + polish → safety + gaps + verify  

### Suggested MVP Scope

**US1 alone** for first demo (eligible enqueue + non-blocking). Practical research value needs **US1+US2** before claiming enrichment coverage.

---

## Notes

- Agents must not tick `checklists/b-featured-enrichment.md` `[x]` boxes.
- Do not harm live burn-in databases; use disposable Postgres for migrations/gates.
- Caps and cutoff are versioned; revise after ops data without reopening the reject list.
- Commit only when the operator asks; keep unrelated concerns in separate PRs.
