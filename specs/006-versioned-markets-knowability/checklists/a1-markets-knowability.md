# A1 Markets & Knowability Requirements Checklist: Versioned Markets & Knowability (Phase A1)

**Purpose**: Before coding, check that the written A1 requirements are clear and complete enough to build from. This is a review of the *docs*, not a test that the code works yet.
**Created**: 2026-11-23
**Feature**: [spec.md](../spec.md) · [plan.md](../plan.md) · [research.md](../research.md)

**Note**: This is a reviewer-owned requirements-quality checklist.
**Review Ownership**: You (the repository owner of this fork), or someone you designate, decide each `[x]` (constitution 2.1.0).
**Marker Semantics**: `[x]` means “this requirement is written clearly enough.” It does **not** mean the feature is implemented.
**Implementation Gate**: Agents must not tick these boxes for you.

**Focus**: Full A1 (outcome repair + versioned markets + knowability + non-blocking / safety). **Depth**: Standard (peer to A0 `archive.md`).

## Scope & Out of Bounds

- [x] CHK001 Does A1 clearly say what it will **not** build yet (featuring, fingerprints, labels/schedules, retention automation, trading execution)? [Completeness, Spec §Out of Scope; Plan §Summary]
- [x] CHK002 Is A1 explicitly dependent on A0 (opt-in tape, insert key, policy (a), `trade_archive` SLOs) without redefining those contracts? [Consistency, Spec §FR-012, §FR-015; Plan §Summary]
- [x] CHK003 Is “repair first, knowability polish later” stated so repair is not held behind model-on-miss? [Clarity, Spec §FR-003; Research Decision 8]



## Opt-In, Cutover & Forward-Only Repair

- [x] CHK004 Is outcome repair a **separate** explicit setting that **defaults to off** and requires archive writing on? [Clarity, Spec §Clarifications Q4, §FR-001; Contract §outcome-repair]
- [x] CHK005 Is it clear that turning archive on does **not** by itself enable repair? [Consistency, Spec §FR-012; Contract §a1-config-and-health]
- [x] CHK006 Is default repair **forward-only** (no required catch-up of pre-enable / early tape)? [Clarity, Spec §Clarifications Q1, §FR-001; US1 §5]
- [x] CHK007 Is a durable cutover instant (`repair_enabled_at` or equivalent) required so analysis/KPI can exclude pre-cutover rows? [Completeness, Spec §FR-018; Research Decision 1]
- [x] CHK008 Are env names and defaults for repair lag and unrepaired ceiling written in the plan/contracts (not only “minutes” / “≤5%” prose)? [Measurability, Plan §Performance Goals; Contract §outcome-repair; Research Decision 6]



## Outcome Repair Behavior & KPI

- [x] CHK009 Are repaired fields and allowed statuses (`ok` / `unrepaired` / `not_needed`, plus A0 `not_attempted`) spelled out, with **never invent an outcome**? [Completeness, Spec §FR-001; Data Model §OutcomeRepair]
- [x] CHK010 Is the repair population for KPI clearly limited to **post-cutover** rows so pre-enable rows do not fail the unrepaired metric by themselves? [Clarity, Spec §FR-004; Contract §outcome-repair Population]
- [x] CHK011 Are thin-label / usable-label / map-failure cases covered in acceptance scenarios? [Coverage, Spec §US1]
- [x] CHK012 Is the Phase C primary-label gate documented (filter to `ok`/`not_needed` or explicit unrepaired stratum) without implementing Phase C? [Completeness, Spec §FR-005; Contract §a1-config-and-health]
- [x] CHK013 Is the market-metadata source for repair identified as public Gamma (token→outcome), distinct from any knowability model? [Clarity, Spec §FR-001; Data.md Outcome-repair; Contract §outcome-repair]



## Versioned Markets

- [x] CHK014 Is `markets` append-on-change with key `(condition_id, known_at)` (or equivalent) and snapshot join `known_at` ≤ `trade_ts` required? [Completeness, Spec §FR-006; Contract §versioned-markets; Data Model §MarketsVersion]
- [x] CHK015 May markets/knowability writers run when archive is on even if repair is still off? [Consistency, Spec §Clarifications Q5, §FR-006; Research Decision 3]
- [x] CHK016 Is a **minimal** token→outcome map required for repair even if richer knowability fields lag? [Clarity, Spec §FR-007; Research Decision 8]
- [x] CHK017 Are “no in-place overwrite” and “don’t spam identical versions” stated? [Edge Case, Spec §Edge Cases; Contract §versioned-markets]



## Knowability Classification

- [x] CHK018 Is lookup order fixed as override → series → **allowlisted template match before Decision**, with model forbidden from inventing template ids and source recorded? [Completeness, Spec §Clarifications 2026-11-24, §FR-008; Research Decision 16; Contract §knowability]
- [x] CHK018b Is the `a1.v1` allowlist (three ids + default regimes) and dumb normalizer (deterministic slotting + ordered cue rules; ambiguity → miss) specified clearly enough to implement without inventing extra templates? [Clarity, Contract §knowability-templates; Research Decision 17]
- [x] CHK019 Is model-on-miss **effectively on when credentials exist** (force-off supported), with write-through to caches, a hard daily call budget (default 10 000), circuit-breaker, and A1 acceptance still possible without a live vendor? [Clarity, Spec §Clarifications 2026-11-24, §FR-008; Research Decision 7; Contract §knowability]
- [x] CHK020 Are regimes (`never_early` / `always_latent` / `windowed` / `unknown`) and `windowed` onset rules stated, including not forcing earnings-style into `windowed`? [Coverage, Spec §FR-009; Contract §knowability]
- [x] CHK021 Is it clear fills in all regimes (including `never_early` and `unknown`) stay on the tape? [Consistency, Spec §FR-009]
- [x] CHK022 On regime upgrade, is the versioned `markets` join authoritative and historical trades knowability columns **not** rewritten? [Clarity, Spec §Clarifications Q2, §FR-011]
- [x] CHK023 Is featuring backfill of already-stored hot fills explicitly deferred to Phase B? [Completeness, Spec §FR-011, §Out of Scope]



## Non-Blocking, Health & Safety

- [x] CHK024 Do requirements forbid blocking observation emission or trades insert on Gamma / repair / classification? [Completeness, Spec §FR-002, §US5; Research Decision 5]
- [x] CHK025 Is it specified that repair KPI / lag must **not** alone redefine A0 `trade_archive` `down` / fail `/ready` (unless a later 003 amendment)? [Consistency, Spec §FR-012; Contract §a1-config-and-health]
- [x] CHK026 Does constitution IV remain intact (assessment persist / repair failure must not block authorized alerts)? [Consistency, Spec §FR-013]
- [x] CHK027 Is monitor-only (archive off) behavior clear: no tape repair readiness blocker when there is no tape? [Edge Case, Spec §Edge Cases; Contract §versioned-markets]
- [x] CHK028 Does dry-run still suppress real notifications while allowing durable tape + A1 metadata writes when archive is on? [Clarity, Spec §FR-017]
- [x] CHK029 Is “no trading execution surface” explicit for A1 delivery? [Completeness, Spec §FR-016, §SC-006]



## Acceptance Criteria & Traceability

- [x] CHK030 Are success criteria measurable for post-cutover repair completion/KPI visibility, snapshot joins, lookup order, and non-blocking insert under Gamma failure? [Measurability, Spec §SC-001–SC-005]
- [x] CHK031 Do plan/contracts name concrete settings (`ARCHIVE_OUTCOME_REPAIR_*`, `ARCHIVE_KNOWABILITY_MODEL_ENABLED`, `ARCHIVE_KNOWABILITY_MODEL_MAX_CALLS_PER_DAY`) consistently with the spec? [Consistency, Plan; Contracts §a1-config-and-health; Spec §FR-001, §FR-008]
- [x] CHK032 Are A1 gaps G-044–G-046 owned in the gap-register with Open dispositions until implement evidence? [Traceability, Gap-register; Research Decision 9]
- [x] CHK033 Is isolation from a live operator burn-in DB called out for migrations/tests? [Assumption, Research Decision 10; Quickstart]



## Notes

- Mark items `[x]` only after **you** confirm the written requirements are clear enough.
- Leave items unchecked when wording is still fuzzy or missing.
- `$speckit-implement` may treat unchecked reviewer items as a gate; agents must not mark them for you.
- Author-owned `checklists/requirements.md` is separate (specify/clarify lifecycle).
- After this checklist is reviewed, next Spec Kit step is `$speckit-tasks` with `SPECIFY_FEATURE_DIRECTORY=specs/006-versioned-markets-knowability`.

