# Tasks: Versioned Markets & Knowability (Phase A1)

**Input**: Design documents from `specs/006-versioned-markets-knowability/`  
**Prerequisites**: `spec.md` (clarified through 2026-11-24), `plan.md`, `research.md`, `data-model.md`, `contracts/*.md` (incl. `knowability-templates.md`), `quickstart.md`, reviewer-owned `checklists/a1-markets-knowability.md` (markers owned by the repository owner; agents leave unchecked). A0 (`005-research-trade-archive`) on `main`.  
**Gaps**: G-044–G-046 **Closed** 2026-11-25 — see [`evidence/g044-g046-verification.md`](evidence/g044-g046-verification.md).

**Tests**: Every behavior change begins with a failing test where practical. `unittest.mock` is prohibited; use working fakes, disposable Postgres, httpx transport fakes, and real value objects per `specs/002-reproducible-runtime/contracts/test-quality.md`. Do **not** point destructive migrations/tests at a live operator burn-in `DATABASE_URL` without consent (Research Decision 10).

**Ops note**: Keep A0 insert path non-blocking under slow/failing Gamma/repair/knowability (US5).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no incomplete dependencies)
- **[Story]**: Maps to `US1`–`US5` from `spec.md`

---

## Phase 0: Human Validation Gate

- [x] T001 Record repository-owner human validation authorizing `$speckit-implement` for slice `006-versioned-markets-knowability` in `specs/006-versioned-markets-knowability/tasks.md` (checklist `a1-markets-knowability.md` markers remain owner-owned) [Constitution §Development Workflow 3–4]
  - Validated 2026-11-24 by repository owner: “Go ahead” (authorize implement after analyze remediations).

---

## Phase 1: Setup (Config + Package Surface)

**Purpose**: A1 settings and module skeleton without changing runtime behavior yet

- [x] T002 Extend `ArchiveSettings` in `src/polymarket_insider_tracker/config.py` with `ARCHIVE_OUTCOME_REPAIR_ENABLED` (default `false`), `ARCHIVE_OUTCOME_REPAIR_LAG_SECONDS` (300), `ARCHIVE_OUTCOME_REPAIR_UNREPAIRED_MAX_RATIO` (0.05), `ARCHIVE_KNOWABILITY_MODEL_ENABLED` (default `true`), `ARCHIVE_KNOWABILITY_MODEL_MAX_CALLS_PER_DAY` (10000), plus OpenAI Decisions credential fields (secret-safe); document in `.env.example` [FR-001, FR-008, FR-012, FR-018]
- [x] T003 [P] Add failing config/summary tests for repair/model defaults and redaction in `tests/test_config.py` [FR-012, Contract §a1-config-and-health]
- [x] T004 Create A1 modules under `src/polymarket_insider_tracker/ingestor/archive/` per `plan.md` (`markets.py`, `knowability.py`, `outcome_repair.py`, `repair_kpi.py`, Decisions adapter stub) without wiring workers yet

**Checkpoint**: Config exists; runtime still A0-only behavior

---

## Phase 2: Foundational (Schema + Cutover State)

**Purpose**: Blocking storage for all stories

**⚠️ CRITICAL**: No user-story workers until this phase completes

- [x] T005 [P] Write failing migration/schema tests for versioned `markets`, knowability series/template caches, human overrides table, and `repair_enabled_at` on collector/A1 state (upgrade + downgrade on disposable Postgres) in `tests/storage/test_research_trade_archive_a1_schema.py` [G-044–G-046, FR-006, FR-018]
- [x] T006 Implement Alembic revision `alembic/versions/rev_*_research_trade_archive_a1.py` with downgrade path per `data-model.md` [FR-006, FR-010]
- [x] T007 [P] Add SQLAlchemy models in `src/polymarket_insider_tracker/storage/models.py` for markets versions, series/template caches, overrides, cutover field [Data Model]
- [x] T008 Implement repository helpers in `src/polymarket_insider_tracker/storage/repos.py` for append-on-change markets, snapshot read (`known_at` ≤ `t`), cache/override upserts, set-once `repair_enabled_at`, and post-cutover trades repair column updates [FR-006, FR-011, FR-018]

**Checkpoint**: Schema + repos ready; no worker wiring

---

## Phase 3: User Story 3 — Versioned Markets Dimension (Priority: P1)

**Goal**: Append-on-change `markets` with token→outcome map; snapshot joins; writers may run when archive on even if repair off

**Independent Test**: Two versions for one `condition_id`; fills before/after second `known_at` resolve different snapshots; identical attributes do not spam versions

### Tests

- [x] T009 [P] [US3] Write failing tests for append-on-change + snapshot join in `tests/storage/test_markets_versioning.py` [FR-006, SC-003, G-045]
- [x] T010 [P] [US3] Write failing tests that markets writer runs with `ARCHIVE_ENABLED=true` and `ARCHIVE_OUTCOME_REPAIR_ENABLED=false` in `tests/ingestor/test_markets_writer_archive_on.py` [FR-006, Clarifications Q5]

### Implementation

- [x] T011 [US3] Implement markets writer + snapshot helper in `src/polymarket_insider_tracker/ingestor/archive/markets.py` (minimal `token_outcomes` required) [FR-006, FR-007, Contract §versioned-markets]
- [x] T012 [US3] Wire markets warm path into pipeline when `ARCHIVE_ENABLED=true` in `pipeline_components.py` / `pipeline.py` (async/non-blocking relative to insert) [FR-002, FR-006]

**Checkpoint**: Versioned markets usable for repair lookups

---

## Phase 4: User Story 1 — Async Outcome Repair (Priority: P1) 🎯 MVP

**Goal**: Forward-only repair after explicit enable + durable cutover; never invent; never block insert

**Independent Test**: Post-cutover thin → `ok`/`unrepaired`; usable → `not_needed`; pre-cutover untouched; Gamma disagree on usable API stays `not_needed`; slow Gamma does not stall insert

### Tests

- [x] T013 [P] [US1] Write failing forward-only / cutover / never-invent tests in `tests/ingestor/test_outcome_repair_forward_only.py` [FR-001, FR-018, SC-001, G-044]
- [x] T014 [P] [US1] Write failing non-blocking insert under slow/failing Gamma repair in `tests/ingestor/test_outcome_repair_nonblocking.py` [FR-002, SC-002, US5 overlap]
- [x] T015 [P] [US1] Write failing usable-API-vs-Gamma disagreement test (`not_needed`, no overwrite) in `tests/ingestor/test_outcome_repair_api_gamma_disagree.py` [Clarifications 2026-11-24, Contract §outcome-repair]

### Implementation

- [x] T016 [US1] Implement set-once `repair_enabled_at` + enable gate in `src/polymarket_insider_tracker/ingestor/archive/state.py` (or sibling) [FR-018]
- [x] T017 [US1] Implement async outcome repair worker in `src/polymarket_insider_tracker/ingestor/archive/outcome_repair.py` (population = observed/insert ≥ cutover; thin→map; usable→`not_needed`) [FR-001, FR-003]
- [x] T018 [US1] Wire repair worker only when archive on **and** `ARCHIVE_OUTCOME_REPAIR_ENABLED=true` in `pipeline.py` / `pipeline_components.py` [FR-001, FR-012]

**Checkpoint**: Repair MVP works; KPI alarms may still be stubbed

---

## Phase 5: User Story 2 — Outcome-Repair KPI Visible (Priority: P1)

**Goal**: Post-cutover thin-row lag + unrepaired ratio metrics/alarms; repair lag must not alone mark `trade_archive` down

**Independent Test**: Drive not_attempted-after-lag and unrepaired ratio across ceilings; pre-cutover excluded; `/ready` tape rules unchanged

### Tests

- [x] T019 [P] [US2] Write failing KPI/metric tests in `tests/ingestor/test_outcome_repair_kpi.py` [FR-004, SC-005, G-044]
- [x] T020 [P] [US2] Write failing test that repair KPI degraded ≠ `trade_archive` down / ready fail in `tests/ingestor/test_outcome_repair_health_isolation.py` [FR-012, Contract §a1-config-and-health]

### Implementation

- [x] T021 [US2] Implement repair KPI signals/metrics in `src/polymarket_insider_tracker/ingestor/archive/repair_kpi.py` (+ prometheus hooks) [FR-004]
- [x] T022 [US2] Register optional `outcome_repair` diagnostic/health signal without redefining A0 tape SLOs in `ingestor/health.py` / pipeline wiring [FR-012, FR-013]

**Checkpoint**: Operators can see repair quality without false tape-down

---

## Phase 6: User Story 4 — Knowability Classification (Priority: P2)

**Goal**: Override → series → `a1.v1` template match → Decisions; credential-gated model; budget/circuit; no invented templates; markets join authoritative on upgrade

**Independent Test**: Lookup-order fixtures; template positives/near-misses; model write-through to series only; over-budget → `unknown` without stall; no historical trades knowability rewrite

### Tests

- [x] T023 [P] [US4] Write failing lookup-order + override tests in `tests/ingestor/test_knowability_lookup_order.py` [FR-008, SC-004, G-046]
- [x] T024 [P] [US4] Write failing `a1.v1` template normalizer fixtures in `tests/ingestor/test_knowability_templates.py` [Contract §knowability-templates, Decision 17]
- [x] T025 [P] [US4] Write failing model budget/circuit/credentials-absent tests in `tests/ingestor/test_knowability_model_guardrails.py` [FR-008, Decision 7/11]
- [x] T026 [P] [US4] Write failing test that regime upgrade does not rewrite historical trades knowability columns in `tests/ingestor/test_knowability_no_trades_rewrite.py` [FR-011, Clarifications Q2]
- [x] T026b [P] [US4] Write failing tests that `windowed` requires onset/`knowable_from`, and that `never_early` / `unknown` fills remain admitted on the trades tape in `tests/ingestor/test_knowability_regimes_admit.py` [FR-009, SC-004]

### Implementation

- [x] T027 [US4] Implement override table usage + series/template caches in `src/polymarket_insider_tracker/ingestor/archive/knowability.py` [FR-008–FR-010]
- [x] T028 [US4] Implement `a1.v1` allowlist + dumb normalizer per `contracts/knowability-templates.md` in `src/polymarket_insider_tracker/ingestor/archive/knowability_templates.py` (or equivalent) [Decision 16–17]
- [x] T029 [US4] Implement OpenAI Decisions API adapter (force-off, credential gate, daily budget, circuit-breaker, series write-through only) in `src/polymarket_insider_tracker/ingestor/archive/decisions_client.py` (name may vary) [FR-008, Decision 11]
- [x] T030 [US4] Wire knowability classification worker when `ARCHIVE_ENABLED=true` (independent of repair flag) in pipeline assembly [FR-006, FR-008]

**Checkpoint**: Knowability path complete without blocking tape

---

## Phase 7: User Story 5 — Non-Blocking + Monitor Safety (Priority: P1)

**Goal**: Prove A0 insert/alert contracts hold with A1 workers enabled; no execution surface; dry-run still durable for tape/A1 metadata

**Independent Test**: Concurrent slow workers + authorized alert path; dry-run no Discord/Telegram; no place/cancel config

### Tests

- [x] T031 [P] [US5] Write failing/extend tests that assessment persist failure still does not block alerts with A1 enabled in `tests/ingestor/test_trade_archive_assessment_isolation.py` or dedicated module [FR-013, SC from 003/005]
- [x] T032 [P] [US5] Write failing test that dry-run + archive + repair/markets writes remain durable without notifications in `tests/ingestor/test_a1_dry_run.py` [FR-017]
- [x] T033 [P] [US5] Extend `tests/test_archive_no_execution_surface.py` (or sibling) so A1 settings/docs introduce no execution surface [FR-016, SC-006]

### Implementation

- [x] T034 [US5] Audit pipeline wiring so markets/repair/knowability tasks cannot await on the Archive insert hot path; fix any regressions in `pipeline.py` / `trade_poller.py` / archive workers [FR-002, FR-016]

**Checkpoint**: Safety contracts green with A1 features present

---

## Phase 8: Polish & Cross-Cutting

- [x] T035 [P] Align `specs/006-versioned-markets-knowability/quickstart.md` with real module/test paths after implement
- [x] T036 [P] Document A1 flags, Decisions credentials, cutover, template allowlist, and the Phase C primary-label gate (`outcome_repair_status` ∈ {`ok`, `not_needed`} or explicit unrepaired sensitivity stratum; A1 does not implement labels) in `README.md` / `.env.example` (no secrets) [FR-005]
- [x] T037 Update `specs/audit/gap-register.md` dispositions for G-044–G-046 with evidence pointers (remain Open until proven; append receipts)
- [x] T038 Run Spec Kit converge against `006` artifacts; append any remaining work as new tasks rather than rewriting history
- [x] T039 Run required verification on a disposable DB / clean tree: `uv run python scripts/verify.py --profile static` and services profile as applicable; record honest results in slice evidence if claimed

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 0**: Human validation before implement
- **Phase 1 Setup**: Immediate after T001
- **Phase 2 Foundational**: Blocks all stories
- **Phase 3 US3 (markets)**: Before US1 repair (token map dependency)
- **Phase 4 US1 (repair)**: MVP after markets
- **Phase 5 US2 (KPI)**: After repair worker exists
- **Phase 6 US4 (knowability)**: After foundational; parallelizable with US2 after markets exist
- **Phase 7 US5**: After workers wired (can start tests earlier)
- **Phase 8 Polish**: After desired stories complete

### User Story Dependencies

- **US3**: After Phase 2 — no story deps
- **US1**: After US3 minimal markets writer
- **US2**: After US1
- **US4**: After Phase 2 (+ markets helpful); independent of repair enable
- **US5**: Cross-cutting after wiring

### Parallel Opportunities

- T003 ∥ T004 after T002
- T005 ∥ T007 after plan freeze
- T009 ∥ T010; T013 ∥ T014 ∥ T015; T019 ∥ T020; T023–T026b; T031–T033
- US4 implementation can proceed in parallel with US2 once Phase 3 done

---

## Parallel Example: User Story 1

```bash
# Failing tests first:
Task: tests/ingestor/test_outcome_repair_forward_only.py
Task: tests/ingestor/test_outcome_repair_nonblocking.py
Task: tests/ingestor/test_outcome_repair_api_gamma_disagree.py
```

---

## Implementation Strategy

### MVP First

1. Phase 0–2 → schema/config  
2. Phase 3 US3 → markets  
3. Phase 4 US1 → forward-only repair (**MVP**)  
4. Stop and validate repair independently  

### Incremental

5. US2 KPI → US4 knowability → US5 safety hardening → Polish/verify  

### Suggested MVP scope

**US3 + US1** (markets map + forward-only repair). KPI and knowability follow.

---

## Notes

- Prefer disposable Postgres for A1 migrations/tests while any burn-in DB remains in use
- Complexipy ≤5 / C901 ≤10 / no `unittest.mock`
- Do not mark reviewer checklist items `[x]` for the owner
- Next after tasks: `$speckit-analyze`, then human validation (T001), then `$speckit-implement`


## Implement evidence (2026-11-24)

- Static profile: `uv run python scripts/verify.py --profile static` → **passed** (lock/format/lint/mypy/pyright/vulture/complexipy/cyclomatic).
- A1 unit suite: **146 passed**, 1 skipped (disposable Postgres migration requires `RUN_SERVICE_TESTS=1`).
- Live burn-in `DATABASE_URL` was **not** migrated; use a disposable DB before enabling A1 workers against production tape.

## Implement evidence (2026-11-25) — repair KPI wiring

- Repair worker now loads thin post-cutover counts each pass and publishes lag / unrepaired KPIs to `outcome_repair` health + Prometheus (`refresh_repair_kpi`).
- Unit proof: `tests/ingestor/test_outcome_repair_kpi_wiring.py` (lag breach + unrepaired population).

## Verification evidence (2026-11-25) — G-044–G-046

- Focused suite + disposable migration: **45 passed** (`RUN_SERVICE_TESTS=1`).
- Static profile: **passed**.
- Services profile: **passed** (probe; redis-contract 52; migrations on `pit_verify_66580d29a13644e0b2116478d8ba3e92` head↔`-1`↔head through `006_research_trade_archive_a1`).
- Burn-in `polymarket_tracker` was not migrated by these gates.
- Full receipt: [`evidence/g044-g046-verification.md`](evidence/g044-g046-verification.md).

## Follow-on (2026-11-25) — question-text cache

- Table `knowability_question_cache` (Alembic `007_knowability_question_cache`); lookup after series, before template/model; model write-through for non-`unknown`.
- Tests: `tests/ingestor/test_knowability_question_cache.py`.
- Burn-in upgraded to `007_knowability_question_cache` (additive).
