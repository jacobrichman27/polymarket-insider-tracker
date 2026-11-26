# Feature Specification: Versioned Markets & Knowability (Phase A1)

**Feature Branch**: `006-versioned-markets-knowability`

**Created**: 2026-11-23

**Status**: Tasks generated (2026-11-24); ready for analyze / human validation / implement

**Input**: User description: "Specify Phase A1 only for the research trade archive: versioned markets dimension, Gamma outcome repair as first-class non-blocking work with a quality KPI, series/template knowability caches with human overrides and optional model-on-miss, and async regime upgrade from provisional unknown—without ever blocking A0 observation emission or trades-tape insert. Do not include featuring budgets, fingerprints, labels, retention automation, or trading execution."

## Clarifications

### Session 2026-11-22

- Q: After A1 ships, should outcome repair also catch up on trades already on the tape (still `not_attempted` / thin labels), or only repair fills inserted after A1 is enabled? → A: Forward-only — repair only fills inserted after A1 repair is enabled; early/pre-A1 tape is not for analysis (operator may delete or ignore it).
- Q: When a market’s knowability regime is classified or upgraded, should A1 also update knowability fields on already-stored trades rows, or should research always read regime from the versioned `markets` snapshot join only? → A: Versioned `markets` join is source of truth; no rewrite of historical trades knowability on upgrade (new inserts may stamp current regime).
- Q: Should the optional cheap model-on-miss path for knowability be off by default until explicitly enabled, or on when model access is configured? → A: Off by default; operator must explicitly enable model-on-miss. **Superseded** by Session 2026-11-24.
- Q: How should “A1 repair is enabled” (the forward-only cutover) be controlled relative to archive writing? → A: Separate explicit setting (default off); requires archive writing on; cutover when the operator enables repair.
- Q: While archive is on but repair is still off, should A1 still write versioned markets / knowability caches? → A: Markets/knowability writers allowed whenever archive is on; repair stays on its own explicit setting.

### Session 2026-11-24

- Q: Revisit model-on-miss default so series/template caches can seed without many human overrides, with spend guardrails. → A: Effective **on when model credentials are configured**; **off** without credentials or when explicitly forced off. Calls only at market/series/template miss grain (never per fill); hard daily budget default **10 000** calls; circuit-breaker on elevated error/timeout rate; over-budget → leave `unknown`, alarm, no insert stall.
- Q: Which model path for knowability miss? → A: **OpenAI Decisions API** (`POST /v1/decisions`, model `gpt-6-luna`) as the default adapter; versioned; swap requires config bump. A1 acceptance still possible with credentials absent / forced off.
- Q: How are human knowability overrides specified? → A: Durable **append-on-change override table** in Postgres (series_id or template_id → regime + notes + `known_at` / policy version). Optional checked-in seed file may bootstrap rows; runtime edits do not require redeploy. Overrides win lookup order.
- Q: Repair cutover clock? → A: Confirmed — population uses collector **observed/insert time** ≥ `repair_enabled_at` (not provider `trade_ts`).
- Q: If API outcome looks usable but Gamma token map disagrees? → A: Usable API → `not_needed` (do not overwrite raw or invent via Gamma). Repair path is for **thin** labels only. Optional disagreement metric/alarm is allowed; silent Gamma overwrite of usable API labels is rejected.
- Q: Early/pre-cutover tape? → A: May remain stored; **not** primary analysis. Filter by cutover / ignore; immediate delete not required.
- Q: Circuit-breaker thresholds, repair-retry detail, other implement knobs? → A: Left to plan/implement within FR/contracts (LLM may choose concrete numbers).
- Q: How should question templates interact with Decision calls? → A: Lookup stays override → series → **allowlisted deterministic template match** → Decisions only on miss. Decisions classifies **this market’s regime** only; it MUST NOT invent or auto-promote new template ids. Empty/minimal template allowlist is OK (series + per-market Decision still work).
- Q: What is the A1 allowlist + dumb normalizer? → A: Version `knowability.templates.v1` reserves three ids — `CRYPTO_UP_OR_DOWN_WINDOW` (`no_private_edge`), `SPORTS_MATCHUP_WINNER` (`private_edge_possible`), `EARNINGS_BEAT_EPS` (`private_edge_possible`). Matching ships disabled; details in `contracts/knowability-templates.md`.
- Q: Binary regimes / drop onset? → A: Operator lock 2026-11-25 — regimes are `no_private_edge` / `private_edge_possible` / `unknown` under `knowability.v3`. No live `knowable_from`; featuring gate is `private_edge_possible` only.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Async Outcome Repair Without Blocking the Tape (Priority: P1)

As a research operator with archive writing enabled, thin public API outcomes (`outcome_index` 999 / empty `outcome`) are repaired asynchronously via token→market metadata so later side-of-market and win/loss work can rely on repaired fields—while every fill still lands on the trades tape immediately without waiting on that repair.

**Why this priority**: A0 deliberately stores raw/thin outcomes. Without A1 repair + KPI, Phase C inherits garbage even though the tape “exists.” Outcome repair is the first A1 priority ahead of knowability polish.

**Independent Test**: Insert or fixture trades with usable API labels and with thin labels **after** A1 repair is enabled; run repair without touching the insert path; verify status transitions, never-invented outcomes, that pre-enable rows are not required to be repaired, and that insert latency/ordering does not wait on repair.

**Acceptance Scenarios**:

1. **Given** archive writing is enabled and a fill inserts **after** A1 repair is enabled with a usable API outcome label, **When** repair evaluates it, **Then** `outcome_repair_status` is `not_needed` (or equivalent) and raw API fields remain unchanged.
2. **Given** a fill inserts **after** A1 repair is enabled with thin API outcome (`999` and/or empty outcome), **When** repair successfully maps `token_id` to market metadata, **Then** repaired outcome fields are set and `outcome_repair_status` becomes `ok`.
3. **Given** a thin-label fill (post-enable) whose token cannot be mapped after required attempts within the versioned lag, **When** repair concludes, **Then** status is `unrepaired`, no invented outcome is stored, and raw API fields remain available.
4. **Given** continuous acquisition is emitting fills, **When** repair work is backlogged or Gamma is slow/failing, **Then** trades-tape inserts and observation emission continue without waiting on repair.
5. **Given** trades already on the tape from before A1 repair was enabled (including early burn-in / non-analysis collections), **When** A1 repair runs, **Then** those pre-enable rows are **not** required to be repaired or caught up; operators may delete or ignore that early tape for analysis.
6. **Given** archive writing is on but the separate repair setting is still off, **When** new fills insert, **Then** they remain unrepaired/`not_attempted` as today and do not enter the post-cutover repair KPI population until repair is explicitly enabled; versioned markets / knowability cache updates MAY still proceed.

---

### User Story 2 - Outcome-Repair Quality Is Operator-Visible (Priority: P1)

As an operator preparing for later labels, I can see and alarm on outcome-repair quality: thin rows stuck in `not_attempted` after the versioned lag, and the unrepaired rate among thin rows over a trailing day—rather than discovering bad `bet_won` only after Phase C.

**Why this priority**: `outcome_repair_status` is a first-class quality KPI locked in `Data.md`; unmonitored repair is rejected.

**Independent Test**: Drive populations of thin rows through attempted / ok / unrepaired / still-not-attempted-after-lag; verify exported rates and alert thresholds match the provisional ceilings (revisable in plan without changing the reject list).

**Acceptance Scenarios**:

1. **Given** archive-enabled operation, **When** operators inspect repair health, **Then** rates for thin-row `not_attempted` after lag and thin-row `unrepaired` share are visible as first-class signals (not buried only in row dumps).
2. **Given** provisional ceilings (attempt within minutes of insert; ≤5% unrepaired among thin rows over a trailing day unless revised with ops evidence), **When** rates breach the versioned threshold, **Then** operators receive an alarm / degraded repair signal distinct from trades-tape `down`.
3. **Given** Phase C primary label design, **When** eligibility is defined, **Then** primary side-of-market / win-loss joins are specified to require `outcome_repair_status` in {`ok`, `not_needed`} (or an explicit unrepaired sensitivity stratum)—A1 documents that gate even though Phase C implements labels.

---

### User Story 3 - Versioned Markets Dimension (Priority: P1)

As a researcher, market metadata (including token→outcome maps and knowability attributes) is stored as an append-on-change versioned dimension keyed by market identity and `known_at`, so trade-time joins use the last version with `known_at` ≤ `trade_ts` and later overwrites do not rewrite history.

**Why this priority**: Snapshot-only Gamma/knowability joins are required for honest reconstruction; mutating a single current row would falsify trade-time attributes.

**Independent Test**: Record two versions for one market with different attributes; join fills at times before and after the second `known_at`; verify each fill sees the correct version and that changes append rather than silent overwrite.

**Acceptance Scenarios**:

1. **Given** new or changed Gamma/knowability attributes for a market, **When** the collector persists them, **Then** a new version row is appended with a new `known_at` rather than mutating prior versions in place.
2. **Given** a fill at `trade_ts`, **When** market attributes are resolved for research join, **Then** the system uses the latest version with `known_at` ≤ `trade_ts` (not a later version).
3. **Given** minimal metadata needed for outcome repair (token→outcome map), **When** A1 ships under scope pressure, **Then** that minimal map is available even if richer knowability caches lag—repair MUST NOT be held behind regime-model polish.

---

### User Story 4 - Knowability Classification via Caches (Priority: P2)

As a research operator, markets receive an information-knowability regime (`no_private_edge`, `private_edge_possible`, or provisional `unknown`) through versioned series/question/template caches, human overrides, and optional model-on-miss—classified at market grain, not per fill, and never blocking A0 insert.

**Why this priority**: Featuring depends on regime honesty; A0 may stamp `unknown` until A1 classifies. Lookup order and regimes are locked in `Data.md` (`knowability.v3`).

**Independent Test**: Seed override, series cache hit, question cache hit, and miss→optional model paths; verify first-hit-wins source recording, binary regimes without onset, and fills continue inserting as `unknown` until upgrade.

**Acceptance Scenarios**:

1. **Given** a market needing classification, **When** lookup runs, **Then** order is human override → series cache → exact question-text cache → allowlisted template match (when enabled) → optional Decision call on miss (when credentials present and not forced off); template match precedes any model call; the model does not invent template ids; `knowability_label_source` records which path won; a successful model result write-through updates the **series** and **question** caches when applicable.
2. **Given** classification under `knowability.v3`, **When** a regime is persisted, **Then** it is one of `no_private_edge` / `private_edge_possible` / `unknown` with no live `knowable_from` onset; timing of privileged knowledge does not create a third class.
3. **Given** classification is not yet available, **When** fills arrive, **Then** they remain admitted on the tape with provisional `unknown` (A0 behavior preserved); A1 MUST NOT drop `no_private_edge` or `unknown` fills from the tape.
4. **Given** a later regime upgrade from `unknown` to a concrete regime, **When** the market version updates, **Then** trade-time research reads the new regime via the versioned `markets` snapshot join (`known_at` ≤ `trade_ts`); A1 MUST NOT rewrite knowability fields on already-stored trades rows. New inserts MAY stamp the current regime when known at insert time. Enqueueing featured enrichment for already-stored hot fills is **Phase B**.
5. **Given** model credentials are configured and the daily call budget is exhausted (or the error circuit is open), **When** a cache miss would otherwise call the model, **Then** the market remains `unknown`, an operator-visible budget/circuit signal fires, and trades insert is not stalled.

---

### User Story 5 - Non-Blocking Relative to A0 and Monitor Safety (Priority: P1)

As an operator, enabling A1 market/repair/knowability work never reintroduces blocking Gamma on the insert path, never replaces the trades tape with assessments, never blocks authorized alerts on assessment persist failure, and never ships trading execution.

**Why this priority**: Hard latency rule across A* phases; constitution I and IV remain in force.

**Independent Test**: Concurrent emission + forced slow/failed Gamma/repair/classification; verify insert and alert paths meet A0 contracts unchanged; confirm no execution surface.

**Acceptance Scenarios**:

1. **Given** archive-enabled acquisition under load, **When** market fetch, repair, or classification is slow or failing, **Then** observation emission and idempotent trades insert still complete under A0 rules (including policy (a) identity retention).
2. **Given** assessment persistence fails in the monitor path, **When** an alert is otherwise authorized, **Then** dispatch is not blocked (constitution IV); repair/knowability failure does not invert that rule.
3. **Given** A1 delivery, **When** operators inspect product capability, **Then** no trading execution, recommendation, or simulated-as-real placement is present.

### Edge Cases

- Gamma / metadata 4xx/5xx and rate limits must degrade repair/classification, not stall the poller or trades insert.
- Token present on the fill but missing from current market metadata → `unrepaired` (or retry while within lag), never invent outcome.
- Usable API outcome that disagrees with Gamma map → stay `not_needed`; never overwrite raw with Gamma; thin labels only enter the repair map path; optional disagreement signal allowed.
- Duplicate classification runs must append markets versions only on real attribute change (or explicit version bump), not spam identical versions.
- Model-on-miss unavailable, credentials absent, forced off, over daily budget, or circuit-open → remain `unknown`; still admit fills; do not stall insert.
- Human override must win over cache and model for the same series/template id until explicitly removed under a new version.
- Mixing knowability policy / model versions in one analysis slice is rejected; version stamps must make slices separable.
- Regime upgrade MUST NOT mutate historical trades knowability columns; snapshot join is authoritative for trade-time regime.
- Monitor-only (archive disabled) deployments: A1 MUST NOT require tape repair health as a readiness blocker when there is no trades tape; document interaction with archive opt-in.
- A1 MUST NOT redefine slice-001 observation identity or A0 `(trade_ts, observation_id)` insert key.
- Pre-A1-repair tape rows left as `not_attempted` are expected under forward-only repair; they are outside the primary analysis population unless an operator later opts into a separate, explicitly versioned catch-up (out of default A1).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A1 MUST provide asynchronous, non-blocking Gamma (or equivalent public market-metadata) outcome repair for durable trades-tape rows **inserted after A1 repair is enabled**: set `outcome_repaired`, `outcome_index_repaired`, and `outcome_repair_status` ∈ {`ok`, `unrepaired`, `not_needed`} (A0 may leave `not_attempted`). Repair enablement MUST be a **separate explicit setting defaulting to off**, and MUST require archive writing to be on. Default A1 is **forward-only**—it MUST NOT require catch-up repair of pre-enable tape rows (operators may delete or ignore early/non-analysis tape). The system MUST NEVER invent an outcome.
- **FR-002**: Outcome repair MUST NOT block observation emission, complete-through progress rules owned by slice 001, or idempotent trades-tape insert owned by slice 005. Admit/knowability/Gamma MUST NEVER wait on the hot insert path.
- **FR-003**: A1’s delivery priority MUST put outcome repair + minimal token→outcome market metadata ahead of optional model-on-miss / regime-polish. Holding repair behind OpenAI Decisions (or any knowability-model) cache niceties is REJECTED.
- **FR-004**: `outcome_repair_status` MUST be a first-class quality KPI with exportable rates and alarms scoped to the **post-enable** repair population: thin API labels still `not_attempted` after a versioned lag (provisional: minutes after insert), and unrepaired share among thin rows over a trailing day (provisional ceiling ≤5%, revisable with ops evidence). Pre-enable rows MUST NOT by themselves fail the unrepaired KPI. Qualitative “repair exists” alone is not acceptance.
- **FR-005**: A1 MUST document the Phase C primary-label gate: side-of-market / win-loss primary joins require `outcome_repair_status` in {`ok`, `not_needed`} or an explicit unrepaired sensitivity stratum. A1 does not implement Phase C labels.
- **FR-006**: A1 MUST introduce a versioned `markets` dimension keyed by market identity (`condition_id` or equivalent locked key) + `known_at`, append-on-change, supporting snapshot joins (`known_at` ≤ `trade_ts`). When archive writing is enabled, markets/knowability writers MAY run even if the separate repair setting is still off (metadata warm-up without entering the post-cutover repair KPI population).
- **FR-007**: Market versions MUST carry attributes needed for repair and knowability provenance (including regime when classified). Minimal token→outcome maps required for repair MUST ship even if richer caches lag. `knowable_from` MAY remain as a nullable legacy column and MUST NOT be required under `knowability.v3`.
- **FR-008**: Knowability classification MUST run at market grain (not per fill) using lookup order: human override → series cache → exact question-text cache → **allowlisted deterministic template match** (when enabled) → optional cheap decision model on miss/low confidence. Template matching MUST run **before** any Decision call when enabled. The model MUST classify regime for the current market only and MUST NOT invent or auto-promote new template ids into the template cache (humans/seed allowlist own template ids). Empty or disabled template matching is acceptable. Model-on-miss MUST be **effectively on when model credentials are configured** and **off** when credentials are absent; operators MUST be able to force it off explicitly. Successful model classifications MUST write through to the **series** cache when a series id is present and to the **question** cache when the question normalizes. Spend guardrails MUST include: (a) no per-fill model calls; (b) hard daily call budget (provisional default **10 000**); (c) circuit-breaker on elevated error/timeout rate; (d) over-budget or circuit-open → leave regime `unknown`, alarm, never stall trades insert. A1 acceptance MUST remain possible without a live model vendor (credentials absent / forced off in tests). The winning path MUST be recorded (`knowability_label_source` or equivalent).
- **FR-009**: Supported regimes under `knowability.v3` are `no_private_edge`, `private_edge_possible`, and provisional `unknown`. There is no third onset-based regime and no live `knowable_from` requirement. Fills in all regimes including `no_private_edge` and `unknown` remain admitted to the trades tape; A1 MUST NOT drop them. Phase B featuring gates on `private_edge_possible` only (plus notional cutoff).
- **FR-010**: Supporting config MUST include versioned `knowability_policy` and versioned series/template caches (append/version on change). Policy changes apply forward under a new policy version.
- **FR-011**: When a market’s regime upgrades from `unknown` (or otherwise becomes classified), A1 MUST persist the new market version so trade-time joins (`known_at` ≤ `trade_ts`) see the correct snapshot. A1 MUST NOT rewrite knowability fields on already-stored trades rows. New inserts MAY stamp the current regime when known at insert time. Enqueueing featuring evaluation for already-stored hot fills is owned by Phase B, not A1.
- **FR-012**: A1 MUST NOT change A0 archive opt-in defaults, policy (a) identity retention, trades insert key, gap-ledger semantics, or `trade_archive` ready SLOs except to add repair/knowability operator signals that do not redefine tape `down` solely as “repair lagging.” Turning archive on MUST NOT by itself enable repair; both settings MUST be independently documented.
- **FR-018**: The durable cutover instant when repair becomes enabled MUST be recorded (or equivalently derivable) so KPI populations and analysis filters can exclude pre-cutover tape without ambiguity.
- **FR-013**: Assessment persistence failure MUST remain observable and MUST NOT block authorized alerts. Repair/knowability failures MUST NOT invert constitution IV.
- **FR-014**: A1 MUST NOT ship featuring budgets, `trade_features`, fill-fingerprint columns, delayed labels/resolutions, automated retention/compaction, wallet/funding dimensions, or trading execution / order placement.
- **FR-015**: Slice 005 remains the trades-tape owner; slice 001 remains observation-boundary owner; slice 003 remains health/readiness owner for tape `down`. A1 extends research metadata and repair quality without inventing a parallel acquisition feed.
- **FR-016**: The product MUST remain research and monitoring only: no placing, simulating-as-real, recommending, or automating trades.
- **FR-017**: Dry-run MUST continue to suppress real notification delivery. When archive writing is enabled, dry-run MUST still allow durable tape writes (A0) and MUST allow A1 durable market/repair updates against that tape without sending Discord/Telegram.

### Key Entities

- **Markets Version**: Append-on-change market metadata row keyed by market identity + `known_at`; source for snapshot joins and knowability attributes.
- **Outcome Repair Result**: Repaired outcome fields plus `outcome_repair_status` on (or joined to) a trades-tape row; never invents labels; KPI-monitored.
- **Knowability Cache Entry**: Versioned series or template classification reused across listings; first-hit-wins with human override.
- **Knowability Policy**: Versioned rules for classification and admit/write provenance applied forward.
- **Regime Upgrade**: Transition from provisional `unknown` to a concrete regime via a new markets version (authoritative for joins); historical trades knowability columns are not rewritten; featuring backfill of historical hot fills is Phase B.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In archive-enabled verification, 100% of fixture fills with thin API outcomes **inserted after A1 repair is enabled** either reach `ok` / `unrepaired` / `not_needed` after the versioned repair lag window, or remain visibly `not_attempted` with an operator-visible lag breach signal—silent permanent `not_attempted` without KPI is a failure. Pre-enable fixture rows need not be repaired for A1 acceptance.
- **SC-002**: Under injected Gamma/metadata failure during repair, trades-tape insert for new observations still succeeds in the same scenarios required by A0 (no insert stall), and no fabricated outcome appears on repaired fields.
- **SC-003**: For a market with two appended versions, fills before and after the second `known_at` resolve different snapshot attributes in deterministic tests (100% of fixture joins correct).
- **SC-004**: Lookup-order tests prove override beats series, series beats template, template beats optional model-on-miss, and `knowability_label_source` matches the winning path in each case.
- **SC-005**: Provisional unrepaired-rate and not-attempted-after-lag signals are observable in operator health/metrics surfaces used for this deployment; breach of the versioned unrepaired ceiling is detectable without querying raw row dumps by hand.
- **SC-006**: No trading execution capability is present after A1 (configuration, CLI, and docs do not offer place/cancel/order paths).
- **SC-007**: A1 verification does not require Phase B featuring, Phase C labels, or Phase D compaction to claim repair + versioned markets acceptance.

## Assumptions

- Phase A0 (`005-research-trade-archive`) is implemented on `main`: opt-in archive, trades tape, gap ledger, policy (a), `trade_archive` readiness.
- Early/pre-A1-repair tape (including local burn-in collections) is not intended for primary analysis; it may remain stored and be ignored/filtered by cutover—immediate delete is not required.
- Knowability model-on-miss default adapter is OpenAI Decisions API (`gpt-6-luna`); human overrides live in a durable Postgres override table (optional file seed).
- Repair cutover is operator-controlled via an explicit setting (default off) distinct from `ARCHIVE_ENABLED`; plan names the setting and how cutover time is recorded.
- Versioned markets / knowability cache writes are gated by archive writing (on), not by the repair setting; repair KPI population remains repair-gated.
- Normative field tables, regimes, lookup order, and outcome-repair locks in root `Data.md` remain authoritative; this slice specifies the A1 delivery bound, not a competing research schema.
- Provisional repair lag (“minutes”) and ≤5% unrepaired ceiling may be revised in plan/clarify with ops evidence without weakening “KPI required” or “never invent outcome.”
- Optional model-on-miss (OpenAI Decisions API / `gpt-6-luna`) is **on when credentials exist**, off otherwise (or when forced off). Daily budget default 10 000 calls. Disabled/miss/over-budget leaves `unknown` rather than blocking admit. A1 acceptance does not require a live model vendor.
- Human overrides are operator-curated research inputs, not trading advice.
- Gap-register will own explicit A1 rows (outcome-repair KPI, versioned markets, non-blocking classification) through plan/tasks/converge; dispositions stay Open until implement evidence.
- Remote analysis access and burn-in calendar thresholds remain operational/analysis concerns; A1 does not build a research UI.
- Constitution research-and-monitoring-only boundary remains in force.

## Out of Scope

- Changing A0 insert identity, fan-out order, policy (a), or gap-ledger classes
- Featuring gate, enrichment arms, `trade_features`, fingerprint_version, signed-flow KPI, regime-upgrade featuring backfill queue (Phase B)
- Delayed `trade_labels` / `market_resolutions` and label-schedule fidelity (Phase C)
- Automated hot→warm compaction / export automation (Phase D)
- Wallet / funding versioned dimensions beyond what repair/knowability strictly need
- Trading decision automation beyond existing monitor scoring, and any execution / order placement
- Redefining slice-001 observation identity or replacing Redis complete-through proof
- Assuming “tape exists ⇒ labels can run” without repair KPI
