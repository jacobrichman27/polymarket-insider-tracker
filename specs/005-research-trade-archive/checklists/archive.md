# Archive Tape Requirements Checklist: Research Trade Archive (Phase A0)

**Purpose**: Review whether Phase A0 observation-bus, durable trades-tape, gap/write-failure ledger, policy-(a) recovery, opt-in config, tape health, capacity, and plane-boundary requirements are complete, clear, consistent, and measurable before tasks/implement.
**Created**: 2026-11-18
**Feature**: [spec.md](../spec.md) · [plan.md](../plan.md)

**Note**: This custom checklist is a reviewer-owned requirements-quality review artifact.
**Review Ownership**: The repository owner of this fork (or a human reviewer they designate) owns the `[x]` judgment (constitution 2.1.0).
**Marker Semantics**: `[x]` means the criterion has been reviewed and satisfied for requirements quality. It does not mean code is complete.
**Implementation Gate**: All newly generated items remain unchecked `[ ]`. Agents must not mark reviewer-owned criteria satisfied.

---

## Scope & Opt-In Compatibility

- [ ] CHK001 Is Phase A0 explicitly bounded to exclude versioned markets, Gamma/Jev, featuring, labels, retention automation, fingerprints, and execution? [Completeness, Spec §Out of Scope; Plan §Summary]
- [ ] CHK002 Is archive writing specified as an explicit setting that defaults to off, with a documented migration note to enable the tape? [Clarity, Spec §Clarifications Q1, §FR-001, §FR-014]
- [ ] CHK003 Are monitor-only (default) vs archive-enabled behaviors distinguished so upgrades do not silently apply checkpoint stall or `trade_archive` readiness? [Consistency, Spec §FR-014; Contract §observation-fanout Modes]
- [ ] CHK004 Is enabling archive without an Archive consumer defined as a wiring/configuration error rather than a silent fall-back to monitor-only? [Edge Case, Contract §observation-fanout Modes; Spec §FR-008]

## Observation Fan-Out & Identity Credit

- [ ] CHK005 Is per-observation consumer order fixed as Archive → Monitor → reserved future slot? [Completeness, Spec §FR-002; Contract §observation-fanout]
- [ ] CHK006 Does the spec state that Archive receives the full trade observation (event + identity + provenance + raw when required) while Monitor may remain trade-event-only in A0? [Clarity, Spec §Clarifications Q3, §FR-002]
- [ ] CHK007 Is identity retention / `EMITTED` credit authorized only after durable Archive insert success under policy (a)? [Clarity, Spec §FR-006; 001 observation-boundary amendment]
- [ ] CHK008 Are Archive-vs-Monitor failure isolation rules complete for: Archive fail, Monitor fail after Archive ok, and Monitor fail when Archive never succeeded? [Coverage, Spec §User Story 2; Contract §observation-fanout Isolation matrix]
- [ ] CHK009 Are crash-between-insert-and-retain semantics specified as idempotent re-delivery then retain (no silent loss / no duplicate fact)? [Edge Case, Spec §FR-003; Contract §observation-fanout Crash cases]
- [ ] CHK010 Is checkpoint advance under archive-enabled mode required to stall while any owed archive-destined observation lacks durable credit? [Completeness, Spec §FR-007; Contract §observation-fanout Checkpoint stall]
- [ ] CHK011 Are marker-only advance, retain-always-with-archive-on, and “permanent-with-alarms only” as the default recovery path explicitly rejected? [Consistency, Spec §FR-008]

## Durable Tape & Persistence

- [ ] CHK012 Is the durable insert key uniquely specified as `(trade_ts, observation_id)` with `observation_id` equal to slice-001 identity (not redefined)? [Clarity, Spec §FR-003–FR-004; Data Model §TradesTapeRow]
- [ ] CHK013 Are A0 section-1 API/cheap-derived fields and status defaults (`outcome_repair_status`, `receipt_status`, provisional knowability) specified without requiring blocking Gamma? [Completeness, Spec §FR-004; Data Model §API / cheap warm fields]
- [ ] CHK014 Is Core hot `raw_row_json` required by default when archive is enabled, with silent omission prohibited and disablement only via an explicit versioned cost flag? [Clarity, Spec §FR-005, §Clarifications; Contract §archive-persistence Raw]
- [ ] CHK015 Is idempotent re-delivery (conflict no-op still authorizing retain) specified so restarts cannot create duplicate fills? [Measurability, Spec §FR-003, §SC-001; Contract §archive-persistence Idempotency]
- [ ] CHK016 Are fingerprint columns explicitly omitted from A0 (Phase B owns them)? [Consistency, Spec §Clarifications Q5, §FR-019]
- [ ] CHK017 Is `risk_assessments` prohibited as a substitute for the trades tape fill grain? [Consistency, Spec §FR-015; Data.md rule 8]

## Gap Ledger & Completeness Honesty

- [ ] CHK018 Are durable gap classes `ingest_loss` and `write_failure` specified with distinct reasons and research stratification? [Completeness, Spec §FR-009; Data Model §IngestGapEvent]
- [ ] CHK019 Is the write-failure lifecycle (`open` → `resolved` on restore; `abandoned` on exhaustion) fully specified? [Clarity, Spec §FR-011; Data Model §State transitions]
- [ ] CHK020 Is A0 completeness honesty defined as ledger-only (no stored per-row/window `data_complete`), with later derivation rules for which statuses spoil windows? [Clarity, Spec §Clarifications Q2, §FR-010]
- [ ] CHK021 Are permanent unreachable holes required to keep abandoned markers, fail derived completeness, alarm, and forbid claiming denominators restored? [Coverage, Spec §FR-011, §SC-003]
- [ ] CHK022 Is the ingest-loss copy path specified so Redis trim (newest ~50) cannot erase research evidence? [Completeness, Spec §FR-009; Contract §archive-persistence Ingest loss copy]

## Tape Health & Constitution IV

- [ ] CHK023 When archive is enabled, is a first-class `trade_archive` readiness component required and distinct from generic database-up? [Completeness, Spec §FR-012; Contract §archive-config-and-health]
- [ ] CHK024 Are provisional tape SLOs quantified (30s / 60s / 5 min) with quiet-market exemption and only `down` failing `/ready`? [Measurability, Spec §FR-012; 003 health-endpoints amendment]
- [ ] CHK025 Is assessment persistence failure explicitly forbidden from marking the tape down or blocking an otherwise authorized alert? [Consistency, Spec §FR-013; Constitution §IV]
- [ ] CHK026 Are monitor-only readiness semantics preserved when archive is disabled (no required `trade_archive` component)? [Consistency, Spec §FR-014]

## `archive_start_at`, Capacity & Planes

- [ ] CHK027 Is `archive_start_at` specified as set once on first archive-enabled collection, durable, and not silently overwritten? [Clarity, Spec §Clarifications Q4, §FR-016]
- [ ] CHK028 Are provisional capacity assumptions (daily partitions, indexes, ~90-day interim retain/detach, raw-on disk budget, alarms) stated as A0 acceptance rather than deferred solely to Phase D? [Completeness, Spec §FR-017, §SC-008; Plan §Provisional capacity]
- [ ] CHK029 Can disk-budget and partition-alarm requirements be objectively verified from the written plan defaults? [Measurability, Plan §Provisional capacity; Research §Decision 8]
- [ ] CHK030 Are data / decision / execution plane boundaries documented such that A0 reserves a future bus slot without shipping order-placement capability? [Completeness, Spec §FR-018, §SC-009]
- [ ] CHK031 Does the product boundary remain research-and-monitoring-only with no place/simulate-as-real/recommend/automate trades language? [Consistency, Spec §FR-021; Constitution §I]

## Cross-Slice Ownership & Traceability

- [ ] CHK032 Does the slice acknowledge slice 001 as observation-boundary owner and slice 003 as health owner (005 implements; does not redefine)? [Consistency, Spec §FR-020; Plan §Dependencies / ownership]
- [ ] CHK033 Are owned gap-register entries G-035–G-043 named and mapped to A0 acceptance without closing them before implement evidence? [Traceability, Plan §Gaps owned; Gap register]
- [ ] CHK034 Are success criteria SC-001–SC-009 measurable without relying on implementation frameworks? [Acceptance Criteria, Spec §Success Criteria]
- [ ] CHK035 Are primary, exception, recovery, and quiet-market scenario classes covered in user stories / edge cases without unresolved contradictions to clarify locks? [Coverage, Spec §User Stories 1–4, §Edge Cases]
- [ ] CHK036 Is the assumption that A1 will own async outcome repair (A0 stamps `not_attempted` / may use `unknown`) stated without making A0 block on Gamma? [Assumption, Spec §Assumptions; FR-004]

## Notes

- Mark items `[x]` only after the fork owner (or designated reviewer) confirms the requirements-quality criterion is satisfied
- Leave items unchecked when they still require clarification, correction, or reviewer evaluation
- `$speckit-implement` reads checklist checkbox state as a gate and must not modify markers
- `checklists/requirements.md` remains the separate author-owned Spec Kit quality checklist
- Focus this round: A0 tape honesty (fan-out, policy (a), ledger, health, capacity, planes); exclude A1–D implementation detail
