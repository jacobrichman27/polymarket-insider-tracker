# Contract: Outcome Repair (A1)

**Feature**: `specs/006-versioned-markets-knowability`  
**Date**: 2026-11-23  
**Depends on**: slice 005 trades tape columns `outcome_*`; public Gamma (or equivalent) market metadata

## Enablement

| Setting | Env | Default | Rules |
| --- | --- | --- | --- |
| Outcome repair | `ARCHIVE_OUTCOME_REPAIR_ENABLED` | `false` | Requires `ARCHIVE_ENABLED=true`; ignored/off when archive off |
| Attempt lag | `ARCHIVE_OUTCOME_REPAIR_LAG_SECONDS` | `300` | Post-cutover thin rows still `not_attempted` after lag → KPI breach signal |
| Unrepaired ceiling | `ARCHIVE_OUTCOME_REPAIR_UNREPAIRED_MAX_RATIO` | `0.05` | Trailing 24h thin post-cutover population |

First transition false→true with archive on MUST persist durable `repair_enabled_at` (no silent overwrite).

## Population

Eligible for repair + KPI: trades with insert/observed time ≥ `repair_enabled_at` only. Pre-cutover rows MUST NOT fail the unrepaired KPI by themselves. Default A1 does **not** catch up pre-cutover rows.

## Behavior

1. Never block trades insert / observation emission / policy (a) retain.
2. Usable API outcome → `not_needed`; leave raw fields unchanged. If Gamma later disagrees, do **not** overwrite raw or flip to a Gamma-invented label; optional disagreement metric/alarm allowed.
3. Thin API (`999` / empty) → map `token_id` via markets `token_outcomes` (fetch/persist markets async as needed).
4. Success → `ok` + repaired fields; failure after attempts → `unrepaired`; never invent.
5. Dry-run: may update durable repair columns when archive on; no Discord/Telegram.
6. Repair/KPI population: collector **observed/insert time** ≥ durable `repair_enabled_at`.

## Rejected

- Inventing outcomes
- Inline Gamma on the Archive insert hot path
- Holding repair behind model-on-miss / knowability polish
- Redefining `trade_archive` `down` solely because repair KPI is degraded
