# Archive Tape Requirements Checklist: Research Trade Archive (Phase A0)

**Purpose**: Before coding, check that the written A0 requirements are clear and complete enough to build from. This is a review of the *docs*, not a test that the code works yet.
**Created**: 2026-11-18
**Feature**: [spec.md](../spec.md) · [plan.md](../plan.md)

**Note**: This is a reviewer-owned requirements-quality checklist.
**Review Ownership**: You (the repository owner of this fork), or someone you designate, decide each `[x]` (constitution 2.1.0).
**Marker Semantics**: `[x]` means “this requirement is written clearly enough.” It does **not** mean the feature is implemented.
**Implementation Gate**: Agents must not tick these boxes for you.

---



## Scope & Opt-In Compatibility

- [x] CHK001 Does A0 clearly say what it will **not** build yet (markets/Gamma, featuring, labels, retention automation, fingerprints, trading)? [Completeness, Spec §Out of Scope; Plan §Summary]
- [x] CHK002 Is archive writing an explicit on/off setting that **defaults to off**, with a note telling operators how to turn the tape on? [Clarity, Spec §Clarifications Q1, §FR-001, §FR-014]
- [x] CHK003 Does the spec keep “monitor only” (default) separate from “archive on,” so an upgrade does not suddenly stall checkpoints or add tape readiness? [Consistency, Spec §FR-014; Contract §observation-fanout Modes]
- [x] CHK004 If someone turns archive on but forgets to wire the archive writer, is that treated as a real config error—not a quiet fall-back to monitor-only? [Edge Case, Contract §observation-fanout Modes; Spec §FR-008]



## Observation Fan-Out & Identity Credit

- [x] CHK005 For each trade, is the delivery order fixed as: Archive first, then Monitor, then a reserved future slot? [Completeness, Spec §FR-002; Contract §observation-fanout]
- [x] CHK006 Does Archive get the full observation (event + identity + provenance + raw when required), while Monitor may still get event-only in A0? [Clarity, Spec §Clarifications Q3, §FR-002]
- [x] CHK007 Is “we’ve handled this trade for the boundary” allowed only **after** a successful durable archive write (policy a)? [Clarity, Spec §FR-006; 001 observation-boundary amendment]
- [x] CHK008 Are the failure cases spelled out for: archive fails; monitor fails after archive succeeded; monitor fails when archive never succeeded? [Coverage, Spec §User Story 2; Contract §observation-fanout Isolation matrix]
- [x] CHK009 If we crash after insert but before remembering the identity, does the spec say we re-deliver safely (no lost fill, no duplicate row)? [Edge Case, Spec §FR-003; Contract §observation-fanout Crash cases]
- [x] CHK010 When archive is on, must the checkpoint wait (stall) until owed archive writes are durable—not advance past unfinished inserts? [Completeness, Spec §FR-007; Contract §observation-fanout Checkpoint stall]
- [x] CHK011 Does the spec clearly reject bad recovery shortcuts: advance-with-marker-only, retain-always while archive is on, and “just alarm and give up” as the default? [Consistency, Spec §FR-008]



## Durable Tape & Persistence

- [x] CHK012 Is each tape row uniquely keyed by `(trade_ts, observation_id)`, using the same identity slice 001 already defines? [Clarity, Spec §FR-003–FR-004; Data Model §TradesTapeRow]
- [x] CHK013 Are the basic fill fields and status defaults listed for A0, and is it clear we do **not** wait on Gamma before inserting? [Completeness, Spec §FR-004; Data Model §API / cheap warm fields]
- [x] CHK014 When archive is on, must we keep the raw provider payload by default—and only turn that off with an explicit versioned cost flag (never silently)? [Clarity, Spec §FR-005, §Clarifications; Contract §archive-persistence Raw]
- [x] CHK015 After a restart, can the same trade be delivered again without creating a second row, while still allowing identity credit on the no-op insert? [Measurability, Spec §FR-003, §SC-001; Contract §archive-persistence Idempotency]
- [x] CHK016 Are fingerprint columns left out of A0 (Phase B owns them)? [Consistency, Spec §Clarifications Q5, §FR-019]
- [x] CHK017 Is it clear that sparse `risk_assessments` rows are **not** a stand-in for the full trades tape? [Consistency, Spec §FR-015; Data.md rule 8]



## Gap Ledger & Completeness Honesty

- [x] CHK018 Does the durable gap ledger separate “provider/feed holes” (`ingest_loss`) from “we saw it but failed to save it” (`write_failure`), with distinct reasons? [Completeness, Spec §FR-009; Data Model §IngestGapEvent]
- [x] CHK019 Is the write-failure lifecycle clear: open → resolved when restored, or abandoned when we give up? [Clarity, Spec §FR-011; Data Model §State transitions]
- [x] CHK020 Does A0 store only the gap ledger for honesty (no per-row `data_complete` flag yet), with rules for how later analysis should treat those statuses? [Clarity, Spec §Clarifications Q2, §FR-010]
- [x] CHK021 For fills that never become saveable, must we keep an abandoned marker, treat completeness as failed, alarm, and **not** pretend denominators are whole? [Coverage, Spec §FR-011, §SC-003]
- [x] CHK022 When Redis trims old loss events (~50 newest), is there still a durable Postgres copy for research? [Completeness, Spec §FR-009; Contract §archive-persistence Ingest loss copy]



## Tape Health & Constitution IV

- [x] CHK023 When archive is on, must `/ready` include a dedicated `trade_archive` status—not just “Postgres is up”? [Completeness, Spec §FR-012; Contract §archive-config-and-health]
- [x] CHK024 Are the tape health thresholds written as numbers (30s / 60s / 5 min), with quiet markets staying up, and only `down` failing readiness? [Measurability, Spec §FR-012; 003 health-endpoints amendment]
- [x] CHK025 If saving a risk assessment fails, does the spec forbid treating that as “tape down” or blocking an alert that was otherwise allowed? [Consistency, Spec §FR-013; Constitution §IV]
- [x] CHK026 With archive off, does readiness stay as today (no required `trade_archive` component)? [Consistency, Spec §FR-014]



## Archive start time, capacity & planes

- [x] CHK027 Is `archive_start_at` set once when archive collection first succeeds, stored durably, and not silently changed on restart? [Clarity, Spec §Clarifications Q4, §FR-016]
- [x] CHK028 Are capacity assumptions for A0 written down now (partitions, indexes, ~90-day keep/detach, disk budget, alarms)—not postponed entirely to Phase D? [Completeness, Spec §FR-017, §SC-008; Plan §Provisional capacity]
- [x] CHK029 From the plan alone, can you tell how to check disk budget and partition/missing-partition alarms? [Measurability, Plan §Provisional capacity; Research §Decision 8]
- [x] CHK030 Are data / decision / execution planes documented so A0 can leave a future bus slot without shipping order-placement code? [Completeness, Spec §FR-018, §SC-009]
- [x] CHK031 Does the product stay research/monitoring only—no placing, faking-as-real, recommending, or automating trades? [Consistency, Spec §FR-021; Constitution §I]



## Cross-slice ownership & traceability

- [x] CHK032 Does 005 say it **implements** the amended 001 boundary and 003 health contracts, without taking ownership away from those slices? [Consistency, Spec §FR-020; Plan §Dependencies / ownership]
- [x] CHK033 Are gaps G-035–G-043 named and tied to A0, and still left Open until there is implement evidence? [Traceability, Plan §Gaps owned; Gap register]
- [x] CHK034 Are success criteria SC-001–SC-009 written so you could measure them without caring which framework the code uses? [Acceptance Criteria, Spec §Success Criteria]
- [x] CHK035 Do the user stories and edge cases cover the main paths (happy, failure, recovery, quiet market) without fighting the clarify decisions? [Coverage, Spec §User Stories 1–4, §Edge Cases]
- [x] CHK036 Is it clear A1 will repair outcomes later, while A0 may insert with `not_attempted` / `unknown` and must not block on Gamma? [Assumption, Spec §Assumptions; FR-004]



## Notes

- Tick `[x]` only when you agree the **requirement text** is good enough—not when code is done
- Leave `[ ]` if something is still unclear or wrong in the docs
- Long-run intent (CHK002): default-off is for safe upgrade / development; after the tape is stable, a later versioned change may make archive the normal default
- `$speckit-implement` may ask before coding if boxes are unchecked; it must not flip these markers
- `checklists/requirements.md` is the separate, smaller Spec Kit author checklist
- This review is about A0 tape honesty only (fan-out, policy a, ledger, health, capacity, planes)—not A1–D build detail

