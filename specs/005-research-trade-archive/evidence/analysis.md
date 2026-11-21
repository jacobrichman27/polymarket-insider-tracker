# Spec Kit Analysis Report: Research Trade Archive (Phase A0)

**Recorded**: 2026-11-18  
**Command context**: `SPECIFY_FEATURE_DIRECTORY=specs/005-research-trade-archive` after `$speckit-tasks`  
**Nature**: Read-only analyze produced findings U1–U4, C1–C2 (0 CRITICAL). Remediation applied in a follow-up edit the same day (this file records both).

## Findings (pre-remediation)

| ID | Severity | Summary |
|----|----------|---------|
| U1 | MEDIUM | Capacity alarms underspecified in tasks |
| U2 | MEDIUM | Locator columns include-vs-defer ambiguous |
| U3 | MEDIUM | Backoff unbounded numerically |
| U4 | MEDIUM | Dry-run × archive unspecified |
| C1 | MEDIUM | SC-006 / FR-007 stall coverage split |
| C2 | LOW | FR-010 untagged |

## Remediation applied

| ID | Change |
|----|--------|
| U1 | Research Decision 12; FR-017 clarified; T034b/T034c; disk 70% ops-runbook |
| U2 | Defer locator/fee columns to Phase B (`data-model.md`, research Decision 4) |
| U3 | 250 ms → ×2 → cap 5 s in FR-007, research, contracts, T020/T024 |
| U4 | FR-022 + T013b; dry-run still writes tape |
| C1 | SC-006 text + T020 tagged SC-006 |
| C2 | FR-010 on T007/T022/T023 |

No CRITICAL constitution conflicts. Ready for human validation (T001) then implement.
