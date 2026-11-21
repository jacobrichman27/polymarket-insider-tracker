# Tasks: Research Trade Archive (Phase A0)

**Input**: Design documents from `specs/005-research-trade-archive/`
**Prerequisites**: `spec.md` (clarified), `plan.md`, `research.md`, `data-model.md`, `contracts/*.md`, `quickstart.md`, amended 001 observation-boundary / 003 health contracts, reviewer-owned `checklists/archive.md` (markers owned by the repository owner; agents leave unchecked).
**Gaps**: G-035–G-043 remain Open until implement evidence; update dispositions through converge.

**Tests**: Every behavior change begins with a failing test where practical. `unittest.mock` is prohibited; use working fakes, `fakeredis`, disposable Postgres/SQLite engines, and real value objects per `specs/002-reproducible-runtime/contracts/test-quality.md`. Spec SC-006 and constitution III require automated fan-out / recovery coverage.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no incomplete dependencies)
- **[Story]**: Maps to `US1`–`US5` from `spec.md`

---

## Phase 0: Human Validation Gate

- [x] T001 Record repository-owner human validation authorizing `$speckit-implement` for slice `005-research-trade-archive` in `specs/005-research-trade-archive/tasks.md` (and optionally mark reviewed items in `checklists/archive.md`) [Constitution §Development Workflow 3–4]
  - Validated 2026-11-20 by repository owner: “Ok everything looks good to me.” Checklist `archive.md` markers remain optional/owner-owned.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Package skeleton and opt-in config surface without changing delivery semantics yet

- [ ] T002 Create `src/polymarket_insider_tracker/ingestor/archive/` package (`__init__.py`, placeholder modules per `plan.md`) 
- [ ] T003 [P] Add `ArchiveSettings` (`ARCHIVE_ENABLED` default `false`, `ARCHIVE_RAW_RETENTION` default `true`) to `src/polymarket_insider_tracker/config.py` and document in `.env.example`
- [ ] T004 [P] Add failing config/summary tests for archive flags (default off; redacted summary) in `tests/test_config.py`

**Checkpoint**: Config exists; runtime delivery still monitor-only retain-always until later phases

---

## Phase 2: Foundational (Schema + Observation Raw)

**Purpose**: Blocking storage and observation payload prerequisites for all stories

**⚠️ CRITICAL**: No user-story delivery wiring until this phase completes

- [ ] T005 [P] Write failing migration/schema tests for partitioned `trades`, `ingest_gap_events`, and `archive_collector_state` (upgrade + downgrade on disposable Postgres) in `tests/storage/test_research_trade_archive_schema.py` [G-035, G-039, G-043]
- [ ] T006 Implement Alembic revision `alembic/versions/rev_*_research_trade_archive_a0.py` with daily UTC partitions (pre-create strategy), indexes from `data-model.md`, and downgrade path [FR-017, G-043]
- [ ] T007 [P] Add SQLAlchemy models in `src/polymarket_insider_tracker/storage/models.py` for `TradeModel`, `IngestGapEventModel`, `ArchiveCollectorStateModel` (no `fill_fingerprint`; no stored `data_complete`; no chain locator/fee columns—Phase B) [FR-010, FR-019]
- [ ] T008 Implement repository helpers in `src/polymarket_insider_tracker/storage/repos.py` for idempotent trades insert and gap upserts [FR-003, FR-009]
- [ ] T009 [P] Write failing tests that parsed observations retain provider raw payload on `TradeObservation` in `tests/ingestor/test_trade_rows.py` (or dedicated module) [FR-005, G-042]
- [ ] T010 Extend `TradeObservation` / parse path in `src/polymarket_insider_tracker/ingestor/trade_rows.py` (and related) to carry raw payload through to archive handoff [FR-001, FR-005, G-042]
- [ ] T011 Implement set-once `archive_start_at` persistence in `src/polymarket_insider_tracker/ingestor/archive/state.py` (refuse silent overwrite) [FR-016]

**Checkpoint**: Schema + raw observation + collector state ready; poller behavior unchanged

---

## Phase 3: User Story 1 — Durable Fill Tape (Priority: P1) 🎯 MVP

**Goal**: When archive is enabled, every admitted observation gets an idempotent `(trade_ts, observation_id)` trades row with section-1 fields and hot raw; quiet fills included; no Gamma wait

**Independent Test**: Bounded fixture of new/repeated/quiet fills → exactly one tape row each; raw present when retention on; insert succeeds with provisional `unknown` / `outcome_repair_status=not_attempted`

### Tests

- [ ] T012 [P] [US1] Write failing tests for idempotent archive insert, quiet-fill persistence without `risk_assessments`, and raw-on default in `tests/storage/test_archive_writer.py` (and/or `tests/ingestor/test_archive_writer.py`) [FR-003–FR-005, FR-015, SC-001, SC-007, G-035, G-042]
- [ ] T013 [P] [US1] Write failing test that archive insert does not call/await Gamma/knowability in `tests/ingestor/test_archive_writer.py` [FR-003]
- [ ] T013b [P] [US1] Write failing test that `DRY_RUN=true` with `ARCHIVE_ENABLED=true` still persists trades (and does not send real notifications) in `tests/ingestor/test_archive_dry_run.py` [FR-022]

### Implementation

- [ ] T014 [US1] Implement archive writer in `src/polymarket_insider_tracker/ingestor/archive/writer.py` (idempotent insert, section-1 mapping, status defaults, raw when enabled, metrics hooks) [FR-003–FR-005]
- [ ] T015 [US1] Wire archive writer into pipeline assembly when `ARCHIVE_ENABLED=true` in `src/polymarket_insider_tracker/pipeline_components.py` / `pipeline.py` (delivery semantics still completed in US2) [FR-001]

**Checkpoint**: Writer can persist observations when invoked; fan-out/retain rules not yet switched

---

## Phase 4: User Story 2 — Failure-Isolated Observation Fan-Out (Priority: P1)

**Goal**: Archive-enabled delivery order Archive → Monitor → reserved slot; Monitor may stay event-only; identity credit only after Archive success; Monitor failure does not undo Archive

**Independent Test**: Inject archive-only fail, monitor-only fail, crash-between insert and retain; assert isolation matrix

### Tests

- [ ] T016 [P] [US2] Write failing poller fan-out tests (happy path; archive fail still invokes monitor / no retain; monitor fail after archive ok retains; crash-between → re-deliver no-op + retain) in `tests/ingestor/test_trade_poller_archive_fanout.py` using harness/fakes [FR-002, FR-006, SC-006, G-036–G-038] (stall coverage is T020; together they satisfy SC-006 including FR-007)
- [ ] T017 [P] [US2] Write failing test that `ARCHIVE_ENABLED=false` preserves monitor-only retain-after-monitor semantics in `tests/ingestor/test_trade_poller_archive_fanout.py` [FR-014]

### Implementation

- [ ] T018 [US2] Refactor `TradePoller` delivery in `src/polymarket_insider_tracker/ingestor/trade_poller.py` to dual-mode fan-out per `contracts/observation-fanout.md` (deprecation adapter for `TradeEvent`-only monitor) [FR-002, FR-006, FR-008, G-036–G-038]
- [ ] T019 [US2] Ensure pipeline passes Archive + Monitor consumers when archive enabled and legacy single callback only when disabled in `src/polymarket_insider_tracker/pipeline_components.py` [FR-001, FR-014]

**Checkpoint**: Policy (a) identity credit works for durable inserts; checkpoint stall/abandon still Phase 5

---

## Phase 5: User Story 3 — Recoverable Write Failures & Honest Holes (Priority: P1)

**Goal**: Checkpoint stall while owed; re-emit until insert; durable gap ledger (`ingest_loss` + `write_failure`); abandon when unreachable; no marker-only advance

**Independent Test**: Transient fail then restore; permanent unreachability → abandoned ledger + alarms; Redis loss mirrored to Postgres

### Tests

- [ ] T020 [P] [US3] Write failing tests for checkpoint stall while owed and bounded retry (250 ms → ×2 → cap 5 s) in `tests/ingestor/test_trade_poller_archive_stall.py` [FR-007, SC-006, G-037, G-040]
- [ ] T021 [P] [US3] Write failing tests for write-failure open→resolved and abandon path in `tests/storage/test_ingest_gap_events.py` [FR-009–FR-011, SC-002, SC-003, G-039–G-040]
- [ ] T022 [P] [US3] Write failing tests that Redis ingest `loss-events` are copied to durable `ingest_gap_events` in `tests/ingestor/test_gap_ledger_mirror.py` [FR-009, FR-010, G-039]

### Implementation

- [ ] T023 [US3] Implement gap ledger in `src/polymarket_insider_tracker/ingestor/archive/gap_ledger.py` (ingest_loss mirror + write_failure lifecycle) [FR-009–FR-011, FR-010]
- [ ] T024 [US3] Implement owed-set tracking, checkpoint stall, retry backoff (250 ms → ×2 → cap 5 s), and abandon-when-unreachable in `trade_poller.py` / archive package per amended 001 contract [FR-007, FR-008, FR-011, G-037, G-040]
- [ ] T025 [US3] Hook boundary loss-event writes to durable ingest_loss copy without inventing a parallel proof model [FR-020, G-039]

**Checkpoint**: Recovery story (a) complete; tape honesty without stored `data_complete`

---

## Phase 6: User Story 4 — Tape Readiness Visible (Priority: P2)

**Goal**: Register `trade_archive` on `/ready` when archive enabled; provisional SLOs; quiet up; assessment persist ≠ tape down

**Independent Test**: Drive owed age / failure windows across 30s/60s/5min; monitor-only omits component; assessment failure does not flip tape down or block alert

### Tests

- [ ] T026 [P] [US4] Write failing health tests for `trade_archive` up/degraded/down and quiet-market exemption in `tests/ingestor/test_trade_archive_health.py` [FR-012, SC-004, G-041]
- [ ] T027 [P] [US4] Write failing test that assessment persist failure does not mark `trade_archive` down / does not block authorized alert attempt in `tests/integration/test_end_to_end.py` or focused module [FR-013, SC-005]

### Implementation

- [ ] T028 [US4] Implement archive health signal provider (oldest owed age, recent failures) in archive package and register `trade_archive` checker when enabled in `src/polymarket_insider_tracker/ingestor/health.py` / `pipeline.py` [FR-012, FR-014, G-041]
- [ ] T029 [US4] Expose Prometheus metrics named/aliased per `contracts/archive-config-and-health.md` [FR-012]

**Checkpoint**: Dual-use readiness matches amended 003 contract

---

## Phase 7: User Story 5 — Extendible Planes Without Trading (Priority: P3)

**Goal**: Document/reserve future bus slot; no execution modules; durable `archive_start_at` stamped on rows; capacity assumptions documented for ops

**Independent Test**: Docs/config offer no place/cancel/order paths; rows carry set-once `archive_start_at`; capacity defaults recorded

### Tests

- [ ] T030 [P] [US5] Write failing tests for set-once `archive_start_at` stamp and no silent overwrite in `tests/ingestor/test_archive_collector_state.py` [FR-016, SC related]
- [ ] T031 [P] [US5] Assert public config/docs surfaces do not expose order-placement settings in a focused docs/config test or checklist evidence note [FR-018, FR-021, SC-009]

### Implementation

- [ ] T032 [US5] Stamp `archive_start_at` from collector state onto trades inserts in writer [FR-016]
- [ ] T033 [US5] Reserve typed future-consumer slot (no-op protocol) in fan-out driver without shipping execution code [FR-018]
- [ ] T034 [P] [US5] Document provisional capacity budget, partition ops expectations, disk≥70% **ops/host** alarm, and archive enable migration note in `README.md` and/or `docs/` cross-links to `quickstart.md` [FR-017, SC-008, G-043]
- [ ] T034b [P] [US5] Write failing tests for in-process missing-partition / partition-miss signal and insert-rate metric exposure in `tests/ingestor/test_archive_capacity_signals.py` [FR-017, SC-008]
- [ ] T034c [US5] Implement missing-partition fail-closed signal and insert-rate Prometheus metric in archive writer / partition helper (disk% remains ops-runbook only) [FR-017, SC-008, G-043]

**Checkpoint**: Plane boundaries honest; burn-in start durable; capacity signals testable

---

## Phase 8: Polish, Verification & Convergence

### Analyze remediation receipt (2026-11-18)

| Finding | Resolution |
| --- | --- |
| U1 capacity alarms | In-process missing-partition + insert-rate (T034b/c); disk 70% ops-runbook (T034) |
| U2 locator columns | Deferred to Phase B (`data-model.md` / research Decision 4) |
| U3 backoff numbers | 250 ms → ×2 → cap 5 s (FR-007, T020/T024, research Decision 3) |
| U4 dry-run × archive | FR-022 + T013b; dry-run still writes tape |
| C1 SC-006 / FR-007 | T020 tagged SC-006; T016 notes stall coverage |
| C2 FR-010 tagging | T007, T022, T023 |

- [ ] T035 [P] Align `specs/005-research-trade-archive/quickstart.md` with actual module/test paths after implement (include dry-run+archive and capacity signal notes)
- [ ] T036 [P] Update `docs/research-archive-roadmap.md` (`implement-tape-a0`) and `Data.md` honesty notes for runtime landed state when verified
- [ ] T037 Update `specs/audit/gap-register.md` dispositions for G-035–G-043 with evidence pointers (remain Open until proven; append receipts rather than rewriting history)
- [ ] T038 Run `uv run python scripts/verify.py --profile static`
- [ ] T039 Run compatibility profile across supported Pythons per slice 002 quickstart
- [ ] T040 Run `uv run --env-file .env python scripts/verify.py --profile services` (migrations + Redis/Postgres)
- [ ] T041 Run `uv run --locked --group dev python -m quality.verify` before merge proposal
- [ ] T042 `$speckit-converge` / evidence receipt that remaining unbuilt work is empty or explicitly deferred

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 0**: Human validation before implement (can overlap checklist review)
- **Phase 1 Setup**: Starts after T001 (or in parallel with checklist review for non-code prep only—**no src behavior until T001**)
- **Phase 2 Foundational**: Depends on Setup; **blocks** US1–US5 delivery work
- **US1 → US2 → US3**: Prefer sequential — writer before fan-out before stall/ledger (shared `trade_poller.py`)
- **US4**: Depends on US2/US3 owed/failure signals
- **US5**: Collector state from Phase 2; stamping integrates with US1 writer; docs can parallel late
- **Phase 8**: After desired stories complete

### User Story Dependencies

| Story | Depends on | Independently testable when |
| --- | --- | --- |
| US1 Tape | Phase 2 | Writer + DB tests pass even if poller still dual-path incomplete |
| US2 Fan-out | US1 writer + Phase 2 | Fan-out harness with injectable archive |
| US3 Recovery | US2 delivery | Stall/abandon/ledger tests |
| US4 Health | US3 owed metrics | Health unit tests with fake clock |
| US5 Planes | Phase 2 state + US1 stamp | State tests + docs review |

### Parallel Opportunities

- T003/T004; T005/T007/T009; T012/T013; T016/T017; T020/T021/T022; T026/T027; T030/T031; T035/T036

---

## Parallel Example: User Story 2

```bash
# After US1 writer exists:
Task: "T016 failing fan-out matrix tests in tests/ingestor/test_trade_poller_archive_fanout.py"
Task: "T017 failing monitor-only default retain tests in tests/ingestor/test_trade_poller_archive_fanout.py"
# Then:
Task: "T018 implement TradePoller dual-mode delivery"
Task: "T019 wire Archive+Monitor in pipeline_components.py"
```

---

## Implementation Strategy

### MVP (US1 only)

1. T001 validation → Phase 1–2 → Phase 3 (US1)
2. Stop: prove idempotent quiet-fill tape via writer tests
3. Then US2–US3 before claiming collection completeness

### Full A0 acceptance

Complete through US4 (health) + US5 (planes/capacity docs) + Phase 8 gates. Marker-only or fan-out-without-stall is **not** acceptance.

### Notes

- Activate every command with `SPECIFY_FEATURE_DIRECTORY=specs/005-research-trade-archive`
- Do not close G-035–G-043 in the register until tests/evidence exist
- Complexipy ≤5 / C901 ≤10 / no mock framework / no suppressions
- Commit only when the repository owner requests it
