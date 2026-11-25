# Contract: A1 Config and Repair Health

**Feature**: `specs/006-versioned-markets-knowability`  
**Date**: 2026-11-23  
**Tape ready owner**: slice 003 / A0 `trade_archive` — unchanged SLOs

## Configuration summary

| Setting | Env | Default |
| --- | --- | --- |
| Archive writing | `ARCHIVE_ENABLED` | `false` (A0) |
| Raw retention | `ARCHIVE_RAW_RETENTION` | `true` (A0) |
| Outcome repair | `ARCHIVE_OUTCOME_REPAIR_ENABLED` | `false` |
| Repair lag seconds | `ARCHIVE_OUTCOME_REPAIR_LAG_SECONDS` | `300` |
| Unrepaired max ratio | `ARCHIVE_OUTCOME_REPAIR_UNREPAIRED_MAX_RATIO` | `0.05` |
| Model-on-miss intent | `ARCHIVE_KNOWABILITY_MODEL_ENABLED` | `true` (effective **on** only with credentials; `false` forces off) |
| Model daily call budget | `ARCHIVE_KNOWABILITY_MODEL_MAX_CALLS_PER_DAY` | `10000` |

`--config-check` MUST show these flags (redacted) and MUST NOT print secrets. Docs MUST state: archive-on does not enable repair; repair requires archive-on.

## Health / metrics

| Signal | Role |
| --- | --- |
| `trade_archive` | A0 tape SLOs only — repair lag MUST NOT alone mark tape `down` |
| `outcome_repair` (component or nested diagnostic) | Optional degraded when post-cutover lag/unrepaired ceilings breach; MUST NOT fail `/ready` solely for repair KPI unless a later 003 amendment says otherwise |
| Metrics | e.g. outcome-repair lag/unrepaired rates; `polymarket_knowability_model_calls_total`, daily budget remaining / exhausted, circuit-open |

Constitution IV: assessment persist / repair worker failure MUST NOT block authorized alerts.

## Phase C gate (documentation)

Primary side-of-market / win-loss joins require `outcome_repair_status` ∈ {`ok`, `not_needed`} or an explicit unrepaired sensitivity stratum. A1 does not implement labels.
