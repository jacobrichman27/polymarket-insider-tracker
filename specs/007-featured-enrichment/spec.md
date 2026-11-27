# Feature Specification: Featured Enrichment (Phase B)

**Feature Branch**: `007-featured-enrichment`

**Created**: 2026-11-25

**Status**: Locally verified (2026-11-26); tasks T001–T057; static/services/`quality.verify` receipts; G-047–G-051 Open; deferred ops audit backlog + T058–T062 logged (not merged)

**Input**: User description: "Start Spec Kit specify for Phase B of the research trade archive: featuring gate (private_edge_possible + versioned notional cutoff), budgeted enrichment arms (markets/receipt/funding/hydrate), optional trade_features, regime-upgrade hot-window featured backfill, lock strong vs weak fill fingerprint and order-as-of contracts, signed-flow/aggressor KPI gate, and two wallet-history stories with wallet_hydrate_status stratification—without labels, retention automation, A0 identity redesign, or trading execution."

## Clarifications

### Session 2026-11-25

- Q: Both-leg featuring policy (FR-017)? → A: **Hybrid (recommended for long-term cost + honesty):** featuring **eligibility** stays per observation (a wallet-leg that clears the gate can be featured). **Shared expensive arms are reused by natural grain**—receipt work once per transaction/fingerprint, funding/hydrate once per proxy/wallet—not blindly doubled when both legs clear (stronger than pure (a)). **Unfeatured opposite/small legs** still get counterparties via **cheap tape fingerprint pair-assist** without forcing them through priority enrichment ((c)). Rejected: full independent double-spend of every arm on both legs with no reuse; rejected: requiring the small leg to clear the notional gate before any counterparty edge exists.
- Q: Notional cutoff and enrichment caps? → A: **$5,000** cutoff locked as the provisional default (versioned). Wall-clock / RPC / hydrate numeric caps stay provisional starting points; **revise after measured enrichment ops data** in plan/implement—not frozen SLOs.
- Q: Classifier-control sample of featuring-rejected `no_private_edge`? → A: **Yes**—keep a small seeded random sample for classifier control; not full enrichment of that population. Exact sample rate left to plan.
- Q: Feature `unknown` by default? → A: **No**—`unknown` featuring stays **off** unless a later explicit versioned policy/config bump opts in with rationale.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Featuring Gate Selects Expensive Enrichment (Priority: P1)

As a research operator with the trades tape and knowability regimes available, only fills that meet the locked featuring gate receive priority enrichment and optional feature snapshots—while all admitted fills remain on the tape for denominators.

**Why this priority**: Without an honest gate, enrichment cost explodes or research silently overclaims coverage on mid-size / `unknown` / `no_private_edge` populations.

**Independent Test**: Fixture fills across regimes and notional sides of the cutoff; verify which rows enter the enrichment queue, that `unknown` / `no_private_edge` stay unfeatured by default (except the documented classifier-control sample), and that tape insert is unaffected.

**Acceptance Scenarios**:

1. **Given** a stored fill whose market regime is `private_edge_possible` and notional is at or above the versioned cutoff, **When** featuring evaluates it, **Then** it is eligible for priority enrichment / optional feature snapshot under the current featuring config version.
2. **Given** a fill with regime `unknown` or `no_private_edge` (and no explicit versioned opt-in for `unknown`), **When** featuring evaluates it, **Then** it is **not** queued for priority enrichment (classifier-control sample for `no_private_edge` remains the only documented exception path).
3. **Given** continuous trades-tape insert, **When** featuring/enrichment is backlogged or disabled, **Then** observation emission and tape insert continue without waiting on enrichment.
4. **Given** a versioned featuring-config / knowability-policy bump that explicitly opts `unknown` into featuring, **When** that config is active, **Then** eligibility follows the new version and older analyses remain interpretable under their recorded versions.

---

### User Story 2 - Budgeted Enrichment Arms With Explicit Statuses (Priority: P1)

As a researcher, featured fills attempt enrichment arms in a locked value order under versioned wall-clock / RPC / hydrate caps, recording per-arm status so null fields never silently mean “not attempted.”

**Why this priority**: Unbounded Gamma → receipt → funding → hydrate fan-out is rejected; Partial arms must remain collectable with honest statuses.

**Independent Test**: Drive featured fills through success, cache reuse, budget skip, failure, and pending paths for each arm; verify degrade-from-bottom order and that Gamma/markets is not skipped for featured rows.

**Acceptance Scenarios**:

1. **Given** a newly featured fill with no caches, **When** enrichment runs within budget, **Then** arms attempt in order: markets/Gamma → receipt decode → Transfer-log funding (on miss/top-up) → lifetime hydrate (on miss), and each arm records a status.
2. **Given** budget pressure, **When** caps would be exceeded, **Then** degrade from the bottom (hydrate → funding → receipt last); markets/Gamma for featured rows is not skipped—failure is recorded and enrichment continues where allowed.
3. **Given** a prior version already satisfies an arm, **When** enrichment runs, **Then** the external call is not redone solely for reuse, but that arm’s status is still recorded for this feature pass.
4. **Given** enrichment cannot finish inside the attempt budget, **When** the attempt ends, **Then** unfinished arms are `pending`, `skipped_budget`, `failed`, or equivalent—never unexplained nulls—and queue retry/abandon rules remain versioned.

---

### User Story 3 - Regime Upgrade Enqueues Hot Featured Backfill (Priority: P1)

As a researcher, when a market’s regime upgrades from `unknown` (or otherwise becomes featuring-eligible) to `private_edge_possible`, already-stored fills still in the hot window that meet the notional cutoff are re-evaluated for featuring—so slow classification does not permanently starve early large fills of enrichment.

**Why this priority**: Insert-time-only featuring under A0→A1 async knowability biases early-window research; Data.md locks hot-window enqueue for Phase B.

**Independent Test**: Store hot fills while regime is `unknown`; upgrade market to `private_edge_possible`; verify enqueue of eligible notional rows not already completed/abandoned for the current enrichment-budget version; verify upgrades to `no_private_edge` do not enqueue; verify rows already left hot are not pretended to be receipt-enrichable without a later amendment.

**Acceptance Scenarios**:

1. **Given** hot fills on a market previously `unknown` that meet the notional cutoff, **When** the market regime becomes `private_edge_possible`, **Then** featuring evaluation is enqueued for those fills under the current enrichment-budget version if enrichment was not already completed or abandoned for that version.
2. **Given** a regime upgrade to `no_private_edge`, **When** backfill runs, **Then** featured enrichment is **not** enqueued (classifier-control sample unchanged).
3. **Given** fills that have already left the hot retention window without enrichment, **When** regime upgrades, **Then** those rows remain on the tape but are **not** claimed as newly receipt-enrichable without an explicit later amendment.
4. **Given** A1 owns regime upgrade writes on versioned markets, **When** Phase B workers observe the upgrade, **Then** enqueue/worker ownership stays in Phase B and MUST NOT rewrite historical trades knowability columns (A1 join rule preserved).

---

### User Story 4 - Fingerprint and Order-As-Of Honesty for Aggregates (Priority: P2)

As a researcher running market-level studies, strong vs weak fill fingerprints are versioned, and order-dependent derived fields record whether they were computed `live_as_of` or `fully_enriched`, so primary studies cannot overclaim match-once volume or live-stable ranks.

**Why this priority**: Observation grain ≠ match grain; weak fingerprints and locator arrival move burst/rank/canonical-leg results.

**Independent Test**: Construct colliding weak keys and receipt-enriched strong keys; materialize features under each order-as-of contract; verify primary-analysis readiness gates and that `live_as_of` rows are not overwritten in place when peers later gain locators.

**Acceptance Scenarios**:

1. **Given** Phase B enrichment can supply `log_index` / `block_number`, **When** fingerprint policy is locked, **Then** a versioned `fingerprint_version` distinguishes strong (tx, token, log_index when present) vs weak (tx, token, price, size) keys and records which was used.
2. **Given** fingerprint-dependent market aggregates (volume, λ, burst, fingerprint-once counts), **When** primary analysis eligibility is evaluated, **Then** those aggregates are **not** analysis-ready for primary studies until the locked fingerprint version is rematerialized (sensitivity strata may use weak with an explicit label).
3. **Given** order-dependent derived fields (burst origin, entry rank, same-second before-this-trade membership, convention canonical-leg when ties remain), **When** they are materialized, **Then** each write records `order_as_of_contract` ∈ {`live_as_of`, `fully_enriched`} (or equivalent) and MUST NOT silently mix contracts in one primary study.
4. **Given** a frozen `live_as_of` feature row, **When** a peer later receives locators, **Then** the frozen row is not overwritten in place; a new feature version and/or `fully_enriched` rematerialization is required if post-receipt order is desired.

---

### User Story 5 - Signed-Flow KPI Before Overweighting λ (Priority: P2)

As a researcher, API `side` on the convention canonical leg remains the market-tape signed aggregate input, while receipt-backed `onchain_direction` / aggressor evidence feeds a published disagreement KPI—and primary overweighting of λ / imbalance waits on that gate.

**Why this priority**: The public trades API has no aggressor role; treating convention-signed flow as aggressor truth is rejected.

**Independent Test**: Cohort with receipt ok/partial; classify agreement/disagreement between API side convention and on-chain direction / maker-taker when exposed; verify KPI visibility and that primary studies remain gated until published for the deployed feature/enrichment cohort.

**Acceptance Scenarios**:

1. **Given** featured fills with `receipt_status` in {`ok`, `partial`}, **When** signed-flow evaluation runs, **Then** disagreement classes (complement / mint–merge / true mismatch / unavailable) are countable as a first-class KPI for the enrichment cohort.
2. **Given** market-tape signed aggregates (λ, imbalance, Yes-equivalent signed notional), **When** computed, **Then** they use API `side` on the fingerprint-deduped convention canonical leg (never arrival order alone claiming on-chain aggressor truth).
3. **Given** the signed-flow KPI is not yet published for the deployed feature version / cohort, **When** primary study or future scoring design is specified, **Then** λ / signed imbalance / initiator features are Useful/sensitivity only or explicitly “convention-signed”—not first-class Core inputs.

---

### User Story 6 - Two Wallet-History Stories Stay Stratified (Priority: P2)

As a researcher, lifetime hydrate (featured Data API walk) and archive-path wallet features remain distinct stories, always stratified by `wallet_hydrate_status`, so lifetime↔archive hybrids are not silently mixed.

**Why this priority**: Data.md locks two wallet-history stories; hydrate is featured-only and Partial.

**Independent Test**: Featured first-sight hydrate complete / partial / skipped_budget; later archive fills for the same wallet; verify status persistence and that analysis contracts require stratification.

**Acceptance Scenarios**:

1. **Given** first featured sight of a proxy with no current wallet version, **When** hydrate runs under budget, **Then** pre-`trade_ts` facts are persisted with `wallet_hydrate_status` reflecting complete, partial, skipped_budget, pending, or failed as appropriate.
2. **Given** `lifetime_is_first_trade`, **When** the hydrate walk is incomplete, **Then** the field is null (true only on a complete empty walk).
3. **Given** research combining hydrate and later archive fills, **When** results are published, **Then** cohorts are stratified by `wallet_hydrate_status` (and related funding exactness flags where used)—silent lifetime↔archive hybrids are rejected.

---

### User Story 7 - Research-Only Surface Preserved (Priority: P3)

As a repository steward, Phase B adds enrichment and feature materialization without introducing place/cancel/order execution surfaces or weakening dry-run / assessment-must-not-block-alerts rules.

**Why this priority**: Constitution research-and-monitoring-only boundary.

**Independent Test**: Config/docs/tests show no execution paths; dry-run still does not deliver notifications; assessment persist failure remains non-blocking for alerts; enrichment failures do not fail trades-tape readiness solely by existing.

**Acceptance Scenarios**:

1. **Given** Phase B settings and docs, **When** inspected, **Then** there is no place/cancel/order execution configuration surface.
2. **Given** dry-run mode with archive and featuring enabled, **When** enrichment runs, **Then** durable research writes may proceed but real Discord/Telegram delivery remains suppressed without poisoning real-delivery dedup.
3. **Given** assessment persistence failure during monitoring, **When** featuring/enrichment is also active, **Then** authorized alert attempts are still not blocked by assessment persist failure (constitution IV).

---

### Edge Cases

- Both legs of one match independently clear the featuring gate (double spend) or only the large leg clears (small opposite leg unfeatured)—tape fingerprint pairing may still supply counterparties without featuring the small leg.
- Receipt locators arrive after a `live_as_of` materialization and would change burst/rank/canonical-leg.
- Funding Dune miss vs Transfer-log window that cannot prove genesis (`first_funding_exact=false`).
- Enrichment abandon after repeated budget skips while the fill is still hot.
- Classifier-control sample of featuring-rejected `no_private_edge` fills (small seeded random)—must not widen into full enrichment of that population by accident.
- Hot-window boundary exactly at upgrade time (fill leaving hot concurrently with enqueue).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST evaluate featuring eligibility using knowability regime `private_edge_possible` AND per-fill notional at or above a versioned cutoff (provisional default $5,000), recording the featuring-config / policy versions used. Legacy `private_settlement_possible` / `private_factor_possible` remain eligible during transition.
- **FR-002**: System MUST NOT feature `unknown` or `no_private_edge` by default; `unknown` opt-in MUST require an explicit versioned policy/config bump with rationale; `no_private_edge` full enrichment MUST NOT replace the small classifier-control sample rule.
- **FR-003**: Featuring and enrichment MUST NOT block observation emission or trades-tape insert (same non-blocking bar as A1 relative to A0).
- **FR-004**: Featured enrichment MUST attempt arms in locked order (markets/Gamma → receipt → Transfer-log funding on miss/top-up → lifetime hydrate on miss) under versioned wall-clock, Polygon RPC, and hydrate page/time caps, recording `enrichment_budget_version`.
- **FR-005**: When over budget, system MUST degrade from the bottom (hydrate → funding → receipt last); MUST NOT skip markets/Gamma for featured rows—record failure and continue as allowed.
- **FR-006**: Every featured enrichment attempt MUST persist per-arm status; null enriched fields are allowed only when status explains them.
- **FR-007**: When a market regime upgrades to featuring-eligible `private_edge_possible`, system MUST enqueue featuring evaluation for already-stored fills that still sit in the hot window, meet the notional cutoff, and have not completed/abandoned enrichment for the current enrichment-budget version.
- **FR-008**: Regime upgrades to `no_private_edge` MUST NOT enqueue featured enrichment; fills already left hot without enrichment MUST NOT be treated as newly receipt-enrichable without a later approved amendment.
- **FR-009**: System MUST lock and version strong vs weak fill fingerprint rules (`fingerprint_version`) and MUST NOT treat weak fingerprints as Core match-once aggregate truth for primary studies until rematerialized under the locked version.
- **FR-010**: Order-dependent derived fields MUST record `order_as_of_contract` (`live_as_of` vs `fully_enriched`); frozen `live_as_of` rows MUST NOT be overwritten in place when peer locators arrive later.
- **FR-011**: Market-tape signed aggregates MUST use API `side` on the fingerprint-deduped convention canonical leg; system MUST publish a signed-flow / aggressor disagreement KPI before λ / imbalance / initiator features may be treated as first-class primary inputs.
- **FR-012**: System MUST keep lifetime hydrate and archive-path wallet features as distinct stories and MUST persist `wallet_hydrate_status` (and related exactness flags where applicable) for stratification.
- **FR-013**: Optional `trade_features` (or equivalent) MAY store derived section 2–6 convenience snapshots for featured rows only; labels and resolution fields MUST NOT be written into trade-time feature rows (Phase C owns labels). **Clarifying disposition (2026-11-26):** this MAY is the B **platform** grain only—**not** acceptance that Data.md §§1–6 Core/Useful catalogs are complete. Hard Core delivery is owned by proposed slice `010-featured-core-features` (G-052 / Phase B.1); Useful follow-on by `011-featured-useful-features` (G-053 / Phase B.2).
- **FR-014**: Versioned `wallets` and `proxy_funding` dimensions MUST support trade-time rematerialization rules (snapshot `known_at` ≤ `trade_ts` for snapshot fields; event-time before `trade_ts` for event-sourced funding/hydrate inputs).
- **FR-015**: Phase B MUST NOT introduce trading execution surfaces; dry-run MUST NOT deliver real notifications or poison real-delivery deduplication; assessment persist failure MUST NOT block authorized alerts.
- **FR-016**: Wash-adjusted market stats remain Useful/Partial diagnostics under the featuring gate (not Core denominators) until enrichment coverage matches the claim or a separate approved gate widens enrichment.
- **FR-017**: For both-leg matches, system MUST use the locked hybrid: per-observation featuring eligibility; **reuse shared enrichment arms by natural grain** (receipt per tx/fingerprint; funding/hydrate per proxy/wallet); **tape fingerprint pair-assist** for counterparties on unfeatured opposite/small legs without requiring them to clear the featuring gate. MUST NOT blindly double every external arm when both legs clear; MUST NOT withhold basic tape-derived counterparty edges until the small leg is featured.

### Key Entities

- **Featured observation**: A trades-tape fill that passed the featuring gate for a given featuring-config / enrichment-budget version.
- **Enrichment attempt**: Versioned effort across arms with statuses, budgets, and optional retries/abandon.
- **Fill fingerprint**: Versioned match-once key (strong when locators exist; weak otherwise) distinct from `observation_id`.
- **Feature snapshot**: Optional durable derived columns (`trade_features` grain) keyed by observation + feature version + order-as-of contract. Full Core/Useful payload completeness is B.1/B.2 (`010`/`011`), not this slice’s SC bar.
- **Wallet / funding versions**: Append-on-change (or event-sourced) dimensions for owner/funding/hydrate facts used at trade time.
- **Featured backfill enqueue**: Work item created on regime upgrade for hot, notional-eligible fills.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In deterministic fixtures, 100% of fills below the notional cutoff or outside `private_edge_possible` (default policy) are excluded from priority enrichment, while gate-passing fills are included.
- **SC-002**: For every featured enrichment attempt in acceptance tests, each arm has an explicit status; zero unexplained null enriched fields.
- **SC-003**: After a regime upgrade fixture from `unknown` to `private_edge_possible`, 100% of hot, notional-eligible, not-yet-completed fills receive a featuring enqueue within the test harness; upgrades to `no_private_edge` enqueue zero featured jobs.
- **SC-004**: Primary-analysis readiness checks reject fingerprint-dependent aggregates and order-dependent ranks unless the locked fingerprint version and declared order-as-of contract are satisfied (or the stratum is explicitly labeled sensitivity-only).
- **SC-005**: Signed-flow disagreement rates are observable as a cohort KPI before any acceptance artifact treats λ / signed imbalance as first-class Core inputs.
- **SC-006**: Wallet-history analyses in acceptance evidence always report `wallet_hydrate_status` stratification; no unlabeled hydrate+archive hybrid cohort.
- **SC-007**: Dry-run + featuring enabled produces zero real notification deliveries and does not introduce execution configuration surfaces.
- **SC-008**: Trades-tape insert path remains non-blocking under enrichment backlog in deterministic tests (insert succeeds without awaiting enrichment completion).

## Assumptions

- Phase A0 trades tape, durable gaps, and Phase A1 versioned markets / knowability / outcome-repair KPI are available; Phase B consumes regime via markets snapshot join and does not redefine A0 identity or A1 cutover rules.
- Notional cutoff provisional default is **$5,000** (versioned). Enrichment numeric caps (~60s wall, ~8 Polygon RPCs, ~10 hydrate pages or ~15s) are starting points to **revise after measured enrichment ops data**; changing them does not reopen the reject list (blocking insert, featuring `unknown` by silent default, marker-only completeness, execution).
- Hot window aligns with A0 retention expectations (configurable within Data.md’s 7–30 day hot band; measured A0 used ~14 day hot sizing).
- Dune funding sync remains scheduled/bulk—not per-fill Dune calls; Transfer logs cover miss/top-up as specified in Data.md.
- Phase C labels/resolutions and Phase D compaction/export are out of scope; wash-adjusted Core promotion needs a separate approval.
- Both-leg policy is locked in Clarifications / **FR-017** (hybrid reuse + tape pair-assist)—not a free choice at implement time.
- A small seeded random **classifier-control** sample of featuring-rejected `no_private_edge` fills is in scope; rate chosen in plan.
- Research operators accept that featuring optimizes enrichment cost, not insider recall; full-tape unsigned denominators remain the honest market base.
- No trading execution, web UI monetization, or constitution change in this slice.
