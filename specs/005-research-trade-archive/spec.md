# Feature Specification: Research Trade Archive (Phase A0)

**Feature Branch**: `005-research-trade-archive`

**Created**: 2026-11-18

**Status**: Tasks generated (2026-11-18); ready for analyze / human validation / implement

**Input**: User description: "Specify Phase A0 only for the research trade archive: ordered observation-bus fan-out of full trade observations (event + identity + provenance + raw), idempotent durable trades-tape inserts for every admitted fill, durable ingest-gap and write-failure ledger that feeds data_complete, policy-(a) recovery (retain identity only after durable archive insert with checkpoint stall), and archive tape readiness when archive writing is enabled. Reuse the existing all-participant poll and complete-through boundary. Do not include versioned markets, Gamma/Jev knowability, featuring, labels, retention automation, or trading execution. Encode data / decision / execution plane boundaries so a later authorized trading consumer can plug in without rewriting the tape."

## Clarifications

### Session 2026-11-18

- Q: After Phase A0 ships, should archive writing be enabled by default for operators who already run the monitor with a database, or only when they turn on an explicit setting? → A: Explicit setting, default off (opt-in archive; monitor-only stays the upgrade default), with a clear migration note to turn it on.
- Q: For Phase A0, should windowed tape completeness be a stored flag on each trades row (or feature row), or only durable gap/write-failure records that later analysis derives completeness from? → A: Gap/write-failure ledger only in A0; later phases derive windowed `data_complete`.
- Q: When archive writing is enabled, must the monitor consumer receive the full trade observation (event + identity + provenance + raw), or is the existing trade-event-only monitor path enough for A0? → A: Monitor may keep trade-event-only in A0; Archive always gets the full observation.
- Q: When an operator first enables archive writing, how should `archive_start_at` (the continuous-collection start used for later burn-in) be set and changed? → A: Set once on first archive-enabled collection; durable; no silent overwrite (explicit operator action + recorded note to change).
- Q: Should Phase A0 store a provisional weak fill fingerprint column on each trades row (from transaction, token, price, and size), omit it entirely until Phase B, or leave it optional? → A: Omit fingerprint columns in A0; Phase B adds them.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Durable Fill Tape for Every Observation (Priority: P1)

As a research operator, when archive writing is enabled I can run the tracker so every admitted public fill becomes a durable trades-tape row keyed by the existing observation identity, including quiet fills that never produce a risk assessment.

**Why this priority**: Without a rebuildable fill tape, market windows, denominators, and completeness analysis cannot be reconstructed from storage. Assessments alone are sparse monitor evidence and must not substitute for the tape.

**Independent Test**: Feed a bounded set of new, repeated, and quiet fills through acquisition; verify each distinct observation appears exactly once on the tape with identity, trade time, section-1 API/cheap-derived fields, and hot raw payload retained by default.

**Acceptance Scenarios**:

1. **Given** archive writing is enabled and required dependencies are ready, **When** a new admitted observation is delivered, **Then** a durable trades-tape row exists for that `(trade_ts, observation_id)` before identity credit is granted.
2. **Given** the same observation is re-delivered after a restart or crash, **When** the archive consumer runs again, **Then** the insert is a no-op (no duplicate fact) and identity credit can complete safely.
3. **Given** a quiet fill that does not trigger detection or an alert, **When** acquisition emits it, **Then** the fill is still present on the trades tape.
4. **Given** classification / market metadata is not yet available, **When** the fill arrives, **Then** the tape insert still succeeds (provisional `unknown` knowability allowed) and does not wait on Gamma, caches, or decision-model calls.

---

### User Story 2 - Failure-Isolated Observation Fan-Out (Priority: P1)

As an operator, one acquisition cycle fans out each observation in fixed order—Archive, then Monitor, with a reserved future decision/execution slot—so archive durability and monitor alerting do not silently depend on each other, and identity credit follows archive success under policy (a). Archive always sees the full observation; the monitor may remain on the trade-event-only adapter in A0.

**Why this priority**: Today’s single-callback retain-always path either skips the tape or can make archive holes permanent after identity is retained. Ordered, isolated fan-out is what makes collection and monitoring coexist on one feed.

**Independent Test**: Inject archive-only failure, monitor-only failure, and crash between successful archive write and identity retention; verify isolation, retain rules, and idempotent recovery match the acceptance scenarios.

**Acceptance Scenarios**:

1. **Given** archive writing is enabled, **When** an observation is delivered, **Then** consumers run in order Archive → Monitor → (reserved future slot); Archive receives the full trade observation, and Monitor may receive trade-event-only via the deprecation adapter.
2. **Given** the archive insert succeeds and the monitor path raises, **When** delivery completes, **Then** the tape row remains, identity is retained, and monitor failure is logged without undoing archive credit.
3. **Given** the archive insert fails, **When** delivery continues, **Then** the monitor path is still invoked with the in-memory observation, identity is **not** retained, and the observation remains eligible for re-delivery while reachable.
4. **Given** archive insert succeeded but the process crashes before identity retention, **When** the tracker restarts and re-delivers the observation, **Then** the idempotent insert no-ops and identity retention then succeeds.
5. **Given** a legacy monitor-only callback wiring with archive disabled (the post-A0 default), **When** the tracker runs, **Then** current monitor-only semantics remain available; archive-enabled runs must not accidentally use retain-always single-callback behavior.

---

### User Story 3 - Recoverable Write Failures and Honest Holes (Priority: P1)

As a research operator, when an archive insert cannot complete I get a restore path (re-emit until durable) rather than a marker-only permanent hole, and when a fill becomes unreachable I get an explicit permanent-loss record, completeness failure for affected windows, and alarms—never a silently advanced complete-through boundary past undurable observations.

**Why this priority**: Markers without restore leave denominators unrestored forever. Advancing the boundary during outage reintroduces permanent holes. Policy (a) plus checkpoint stall is the locked recovery contract.

**Independent Test**: Force transient insert failures that later succeed via re-delivery; force exhaustion / unreachability; verify restore clears the failure set, and permanent cases keep markers, fail completeness, and alarm without claiming denominators are whole.

**Acceptance Scenarios**:

1. **Given** an archive-destined observation lacks a durable insert, **When** the page would otherwise advance the complete-through checkpoint, **Then** the checkpoint stalls past that observation and insert retries with bounded backoff.
2. **Given** a transient archive failure while the fill remains reachable, **When** re-delivery eventually inserts successfully, **Then** the write-failure record is resolved/narrowed, identity may be retained, and the fill contributes to denominators again.
3. **Given** a fill never becomes durable before it ages out of reachable acquisition / recovery horizon, **When** recovery is exhausted, **Then** a durable write-failure gap remains (abandoned), affected window completeness is false, rate/SLO alarms fire, and denominators are not claimed restored for that identity.
4. **Given** ingest loss evidence that today lives only in a short operational buffer, **When** archive writing is enabled, **Then** a durable gap ledger retains ingest-loss and write-failure classes with reasons so research can stratify provider holes vs persist holes after buffer trim; A0 does not also store a per-row windowed `data_complete` flag.

---

### User Story 4 - Tape Readiness Visible to Operators (Priority: P2)

As an operator with archive writing enabled, readiness and health show a first-class trade-archive / trades-tape component with provisional backlog SLOs, without treating assessment-persist failure as tape-down or blocking authorized alerts.

**Why this priority**: “Postgres up for assessments” is not the same as “the research tape is keeping up.” Leaving readiness alone would hide a dead archive behind a green ready signal.

**Independent Test**: Drive owed-insert age and failure windows across the provisional thresholds; verify degraded vs down vs quiet-market-up, and that assessment persistence failure does not flip the tape component to down or suppress an otherwise authorized alert.

**Acceptance Scenarios**:

1. **Given** archive writing is enabled, **When** health is queried, **Then** a `trade_archive` (or equivalent) component is required and distinct from generic database-up for assessments.
2. **Given** any owed insert older than 30 seconds or any insert failure in the last 60 seconds, **When** health is evaluated, **Then** the tape component is at least `degraded` while recovery is in progress.
3. **Given** any owed insert older than 5 minutes, or all attempts failed for 5 minutes with at least one attempt, **When** readiness is evaluated, **Then** the tape component is `down` and readiness fails; quiet markets with no attempts and no backlog stay `up`.
4. **Given** assessment persistence fails inside the monitor path, **When** an alert is otherwise authorized, **Then** dispatch is not blocked, and the failure does not by itself mark the trades tape `down`.
5. **Given** archive writing is disabled (monitor-only), **When** readiness is evaluated, **Then** existing monitor-only readiness semantics apply without requiring the archive component.

---

### User Story 5 - Extendible Planes Without Trading Capability (Priority: P3)

As a product owner, the A0 archive specifies a stable data-plane observation bus and leakage-safe boundaries so a later authorized decision or execution slice can subscribe without rewriting the tape—and without shipping dormant order-placement capability now.

**Why this priority**: Extensibility is a design constraint of this slice; trading remains constitutionally out of product scope until a separate approved change.

**Independent Test**: Review the published plane contract and reserved consumer slot; confirm no execution credentials, order client, or trade-placement path is introduced, and that labels/features are not required for A0 acceptance.

**Acceptance Scenarios**:

1. **Given** the A0 specification and shipped archive-enabled wiring, **When** a future decision/execution consumer is designed, **Then** it can subscribe to the same observation bus after Archive and Monitor without changing trades-tape identity semantics.
2. **Given** A0 delivery, **When** operators inspect product capability, **Then** no trading execution, recommendation, or simulated-as-real placement is present or advertised.
3. **Given** research burn-in needs, **When** fills are stored after archive is first enabled, **Then** each row carries the durable deployment `archive_start_at` established at first archive-enabled collection start; later analysis can apply burn-in without inventing a start time, and the value is not silently overwritten on restart.

### Edge Cases

- Restart or crash after durable insert but before identity retention must re-deliver safely (idempotent no-op + then retain).
- Monitor failure after archive success must not revoke identity or delete the tape row.
- Archive failure must not block monitor invocation, must not retain identity under policy (a), and must not silently advance the complete-through boundary past the undurable observation.
- Empty/quiet acquisition intervals are not archive failure; owed age is measured from first archive-destined delivery attempt for that identity.
- Duplicate provider pages and overlapping windows must not create duplicate tape facts.
- Rows missing optional enrichment (outcome repair, chain locators, funding) must still insert; Partial columns may remain null / `not_attempted`.
- Ingest-loss intervals without a single observation_id remain durable as class `ingest_loss`; write failures at known identity grain use class `write_failure`.
- Legacy single-callback monitor-only mode must remain available when archive is disabled; it must not be the accidental path when archive is enabled.
- Disk/partition pressure under all-participant cold start must surface via capacity alarms rather than silent delete of fills.
- Assessment / alert path failures remain orthogonal to tape readiness (constitution IV).
- With archive writing left at the default off, enabling it later does not rewrite historical monitor-only identity credit; `archive_start_at` is set once at first archive-enabled collection for that deployment and does not silently change afterward.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Archive writing MUST be controlled by an explicit configuration setting that defaults to **off** after A0 ships (monitor-only upgrade default). Documentation MUST include a migration note explaining how and why to enable the research tape. When archive writing is enabled, the system MUST deliver each admitted observation on an ordered observation bus as a full trade observation carrying event, slice-001 identity (`observation_id`), provenance, and provider raw payload (raw retention default on when archive is enabled).
- **FR-002**: Consumer order per observation MUST be Archive → Monitor → reserved future decision/execution slot. Archive MUST receive the full trade observation. Monitor MAY keep the existing trade-event-only path in A0 via a deprecation adapter (full-observation monitor handoff is not required for A0 acceptance). Archive MUST NOT depend on Monitor success; Monitor MUST NOT authorize or revoke identity retention.
- **FR-003**: The archive consumer MUST idempotently persist every admitted observation to the durable trades tape on unique key `(trade_ts, observation_id)` without waiting on Gamma, knowability caches, Jev, featuring, or labels.
- **FR-004**: Trades-tape rows MUST store section-1 fields available from the API row and cheap derived logic at ingest (including Partial API fields such as raw `outcome` / `outcome_index`), MAY stamp provisional knowability `unknown`, and MUST NOT redefine slice-001 identity or size/price canonicalization.
- **FR-005**: Default A0 MUST retain hot `raw_row_json` (or equivalent Core raw capture) through insert. Disabling raw retention MUST require an explicit versioned cost flag that amends Priority/Feasible for that deployment; silent omission because parse succeeded is prohibited.
- **FR-006**: Under locked policy **(a)**, identity retention / emission credit MUST be authorized only after durable archive insert success for that observation. Policy **(b)** (outbox + reconciler) MUST NOT be implemented unless a later versioned slice-001 amendment switches.
- **FR-007**: While any archive-destined observation on the current page (or owed set) lacks a durable insert, the system MUST NOT advance the complete-through checkpoint past that observation; it MUST retry with bounded backoff (provisional: 250 ms initial, ×2, cap 5 s; abandon by reachability/horizon—not a fixed attempt count) and keep the fill eligible for re-delivery without identity credit.
- **FR-008**: Marker-only advance, retain-always single-callback behavior with archive enabled, and “permanent-with-alarms only” as the default recovery path are REJECTED.
- **FR-009**: The system MUST persist a durable gap / write-failure ledger that outlives short operational buffers, with stratified classes at least `ingest_loss` and `write_failure`, reasons compatible with amended slice-001 vocabulary, and status lifecycle that supports open → resolved on restore and abandoned on exhaustion.
- **FR-010**: A0 MUST persist the durable gap/write-failure ledger as the completeness input for later windowed `data_complete` derivation. A0 MUST NOT store a per-trade or per-window `data_complete` column/flag. Ledger semantics MUST ensure open/unresolved ingest losses and open/abandoned write failures spoil affected windows when derived later; resolved write failures MUST stop spoiling once the trades row exists. Classes/reasons MUST remain queryable for sensitivity stratification.
- **FR-011**: A0 acceptance MUST include the policy-(a) restore path: re-emit until insert while reachable; on successful restore, clear or narrow the failure record so denominators can include that identity again; on unreachability/exhaustion, keep permanent markers, fail completeness, fire alarms, and MUST NOT claim denominators restored.
- **FR-012**: When archive writing is enabled, health/readiness MUST expose a first-class `trade_archive` / trades-tape component per the amended slice-003 contract, using provisional SLOs: degraded at 30s owed or failure in 60s; down (fail ready) at 5 min owed or 5 min all-attempts-failed with ≥1 attempt; quiet market with no attempts and no backlog stays up. Only `down` fails readiness.
- **FR-013**: Assessment persistence failure MUST remain observable and MUST NOT block an otherwise authorized alert attempt; it MUST NOT by itself mark the trades tape `down`.
- **FR-014**: Monitor-only deployments (archive writing disabled — the default) MUST keep existing readiness semantics without requiring the archive component, and MUST NOT apply policy-(a) checkpoint stall or tape-down readiness.
- **FR-015**: `risk_assessments` MUST remain optional sparse monitor evidence and MUST NEVER substitute for the trades tape as fill grain.
- **FR-016**: On first successful archive-enabled collection for a deployment, A0 MUST establish a durable UTC `archive_start_at` and stamp it on stored trades rows (and collector/config state). Restarts MUST reuse that value without silent overwrite. Changing it MUST require an explicit operator action with a recorded migration/note. A0 MUST NOT gate live monitor alerts on research burn-in.
- **FR-017**: A0 MUST document and provision provisional capacity assumptions (partition strategy, required indexes, interim retain/detach before Phase D, disk budget with raw-on sizing, and capacity alarms). In-process: missing-partition and insert-rate signals/metrics MUST be exposed; owed backlog feeds `trade_archive`. Disk ≥70% of budget is documented as an ops/host alarm. Qualitative “volume is heavy” alone is not acceptance.
- **FR-022**: When archive writing is enabled, `DRY_RUN` MUST still perform durable archive inserts and gap-ledger writes. Dry-run continues to suppress real notification delivery and must not poison delivery deduplication (slice 003).
- **FR-018**: A0 MUST encode the three-plane extensibility contract: **data** (this tape and later features/labels), **decision** (monitor scoring today; future policy consumer), **execution** (out of product until separately approved). A0 MUST reserve the bus slot and MUST NOT ship order-placement, trading credentials, or dormant execution modules.
- **FR-019**: A0 MUST NOT own versioned `markets` schema, blocking Gamma admit/repair, series/template knowability caches, Jev-on-miss, featuring/enrichment budgets, fill-fingerprint columns (weak or strong), delayed labels/resolutions, or automated hot→warm compaction (those belong to later slices). A0 MUST NOT store a provisional `fill_fingerprint`; Phase B owns fingerprint columns and `fingerprint_version`.
- **FR-020**: Slice 001 remains the observation-boundary owner; slice 003 remains the health/readiness owner. This slice implements those amended contracts and MUST NOT invent a parallel proof or readiness model in logs only.
- **FR-021**: The product MUST remain research and monitoring only: no placing, simulating-as-real, recommending, or automating trades.

### Key Entities

- **Trade Observation**: One admitted acquisition unit carrying trade event, slice-001 identity, provenance, and raw provider payload for bus consumers.
- **Trades Tape Row**: Durable fill fact at grain `(trade_ts, observation_id)`; section-1 API/cheap fields; optional Partial nulls; Core hot raw; `archive_start_at`; provisional knowability may be `unknown`.
- **Gap / Write-Failure Record**: Durable completeness evidence with class (`ingest_loss` | `write_failure`), reason, time bounds or observation_id, status (open/resolved/abandoned), and research-safe detail.
- **Observation Boundary Credit**: Complete-through / identity retention state owned by slice 001; under policy (a), advanced for an observation only after durable archive success, with checkpoint stall while owed inserts remain.
- **Tape Health Component**: Operator-visible archive readiness state (`up` / `degraded` / `down`) distinct from assessment database liveness when archive writing is enabled.
- **Plane Boundary**: Data vs decision vs execution separation; only the data plane ships in archive phases A0–D; execution requires a later approved product-boundary change.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: In archive-enabled verification, 100% of distinct admitted observations in a bounded fixture appear exactly once on the durable trades tape (no silent drops of quiet fills; no duplicates after restart).
- **SC-002**: Under injected transient archive failure, at least one previously failed observation becomes durable via re-delivery without operator manual row invention, and its write-failure record moves out of the open/abandoned spoiling set.
- **SC-003**: Under injected permanent unreachability after failed insert, operators can identify the hole within one readiness/health poll cycle after the abandon condition via an abandoned write-failure ledger row (and tape health/alarms); A0 does not claim denominators restored for that identity, and does not require a stored per-row `data_complete` flag to prove honesty.
- **SC-004**: With archive enabled, a tape outage that meets the 5-minute down SLO causes readiness to fail; a quiet interval with no owed work does not.
- **SC-005**: Monitor-path assessment persistence failure still allows an otherwise authorized alert attempt in the same scenario family already required by safe-operation contracts.
- **SC-006**: Archive-enabled fan-out scenarios (archive fail; monitor fail after archive ok; crash between insert ok and identity retain) and checkpoint-stall-while-owed (FR-007) each have deterministic automated coverage that matches FR-002/FR-006/FR-007.
- **SC-007**: Default raw capture is present on inserted rows in the default configuration; turning raw off is impossible without an explicit versioned configuration path.
- **SC-008**: Provisional capacity (partitions/indexes/interim retain/disk budget/alarms) is written in the plan and provisioned such that a clean archive-enabled bring-up does not rely on Phase D compaction to avoid immediate disk exhaustion under the stated growth assumption.
- **SC-009**: No trading execution capability is present in the delivered product surface after A0 (configuration, CLI, and docs do not offer place/cancel/order paths).

## Assumptions

- Slice 001 observation-boundary / status contracts already amended for policy (a), fan-out isolation, checkpoint stall, and write-failure vocabulary remain authoritative; this slice implements them rather than re-litigating.
- Slice 003 health / pipeline-lifecycle contracts already amended for `trade_archive` and provisional SLOs remain authoritative; this slice wires runtime behavior to those contracts.
- Supported acquisition remains the documented anonymous public all-participant trades poll with existing complete-through boundary, recovery horizon, and possible-data-loss semantics; A0 does not invent a second global feed.
- Archive writing is opt-in via explicit config defaulting to off so existing monitor deployments upgrade without checkpoint stall or tape readiness until operators enable the tape.
- Dry-run with archive enabled still writes the research tape; it only suppresses real notification delivery / dedup side effects.
- Chain locator/fee columns are omitted from the A0 `trades` schema; Phase B adds them.
- Gap-register entries G-035–G-043 are owned through this slice (and prerequisite amendments already recorded); dispositions stay Open until implement evidence lands.
- Provisional tape SLOs (30s / 60s / 5 min) and capacity defaults (daily partitions, ~90-day interim retain/detach, raw-on sizing) may be revised with operational evidence in plan/clarify without changing the reject list (marker-only, leave-ready-alone, blocking Gamma on insert).
- Phase A1 (`006-…`) will own versioned markets and outcome repair asynchronously; A0 may persist `unknown` until then.
- Phase B owns fingerprint columns, quality gates, featuring budgets, and order-as-of enrichment; A0 omits fingerprint storage entirely and must not claim primary volume/λ/burst studies keyed by weak fingerprints.
- Research burn-in calendar/completeness thresholds are analysis contracts for later exports; A0 persists `archive_start_at` and the gap/write-failure ledger only—windowed `data_complete` derivation belongs to later featuring/export work.
- Remote warehouse / analysis access topology (do not download the full tape locally) is an operational assumption documented in the roadmap; A0 does not build a research UI.
- Constitution research-and-monitoring-only boundary remains in force; any future trading slice needs its own approved specification and likely constitution change.

## Out of Scope

- Versioned `markets`, Gamma outcome repair KPI, series/template caches, human overrides, Jev-on-miss (Phase A1)
- Featuring gate, enrichment arms, `trade_features`, wallet/funding dims, strong fingerprint lock, signed-flow/aggressor KPI (Phase B)
- Delayed `trade_labels` / `market_resolutions` and label-schedule fidelity (Phase C)
- Automated hot→warm compaction and long-horizon export automation (Phase D) — interim retain/detach assumptions still required in A0 plan
- Trading decision automation beyond existing monitor scoring, and any execution / order placement
- Policy (b) outbox reconciliation unless a later versioned 001 amendment authorizes the switch
- Redefining slice-001 observation identity or replacing Redis complete-through proof with an archive-only parallel model
- Provisional or strong fill-fingerprint columns (Phase B)
- Chain locator / fee enrichment result columns on `trades` (Phase B)
