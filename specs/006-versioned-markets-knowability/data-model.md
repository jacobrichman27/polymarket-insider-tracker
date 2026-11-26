# Data Model: Versioned Markets & Knowability (Phase A1)

**Feature**: `specs/006-versioned-markets-knowability`  
**Date**: 2026-11-23  
**Normative research fields**: root [`Data.md`](../../Data.md). A0 tape grain remains `(trade_ts, observation_id)` owned by slice 005.

## Entities

### MarketsVersion (`markets`)

Append-on-change dimension. Primary key `(condition_id, known_at)` (or equivalent locked market identity + `known_at`).

| Column | Type | Rules |
| --- | --- | --- |
| `condition_id` | text | Market identity; required |
| `known_at` | timestamptz | Version time UTC; append-only |
| `token_outcomes` | jsonb | Map `token_id` → `{outcome, outcome_index}` (minimal repair surface) |
| `question` / `series_slug` / template keys | text null | Classification inputs when available |
| `info_knowability_regime` | text null | Under `knowability.v3`: `no_private_edge` / `private_edge_possible` / `unknown` |
| `knowable_from` | timestamptz null | Legacy; unused under `v3` (write `NULL`) |
| `knowability_label_source` | text null | override / series / question / template / model / unknown |
| `knowability_policy_version` | text null | Forward-applied policy id |
| `source_version` | text null | Gamma/fetch provenance |
| `raw_market_json` | jsonb null | Optional hot metadata capture (not required for repair acceptance) |

**Validation:** Never mutate a prior `(condition_id, known_at)` row. Append only when attributes change or policy/model version bumps. Snapshot join: latest row with `known_at` ≤ `trade_ts`.

### KnowabilitySeriesCache / KnowabilityQuestionCache / KnowabilityTemplateCache

Versioned cache entries (append-on-change). Keys: `series_slug`, SHA-256 of normalized question text, or allowlisted template id — each scoped by `policy_version` / allowlist version.

| Field | Notes |
| --- | --- |
| regime | Cached classification |
| `question_text` | Question cache only — normalized title for inspection |
| label_source | Path that produced the cache write |

Human overrides: durable append-on-change table keyed by `series_id` or `template_id` (regime, notes, `known_at`, policy version). Optional seed file may bootstrap. Wins lookup order until superseded by a newer override version.

### KnowabilityPolicy

Config/version record (not per fill): policy id, effective_at, ruleset hash/notes. Changes apply forward.

### OutcomeRepair on `trades` (existing A0 columns)

A0 already stores `outcome_repair_status`, `outcome_repaired`, `outcome_index_repaired`. A1 **updates** these for rows with insert/observed time ≥ `repair_enabled_at` when repair is enabled.

| Status | Meaning |
| --- | --- |
| `not_attempted` | A0 default / pre-cutover / repair off |
| `not_needed` | API label usable; no invent |
| `ok` | Mapped via token→markets |
| `unrepaired` | Attempted; no trustworthy map |

**Never invent.** Raw API `outcome` / `outcome_index` remain; repaired fields are additive.

### RepairCutoverState

Extend `archive_collector_state` (or sibling A1 state row):

| Field | Rules |
| --- | --- |
| `repair_enabled_at` | Set once on first successful enable of `ARCHIVE_OUTCOME_REPAIR_ENABLED` with archive on; no silent overwrite |
| `source_id` | Align with A0 collector namespace |

## Relationships

```text
trades.condition_id ──snapshot──▶ markets (known_at ≤ trade_ts)
trades.token_id ──repair──▶ markets.token_outcomes
knowability caches ──classify──▶ new markets version (regime fields)
```

## State transitions

### Repair (post-cutover only)

`not_attempted` → `not_needed` | `ok` | `unrepaired`  
`not_needed` / `ok` / `unrepaired` are terminal for default A1 (no silent flip without new evidence version — plan: leave terminal unless explicit re-repair tool later).

### Markets

No in-place update. Attribute change → new `known_at` version.

## Out of model (later slices)

- `fill_fingerprint`, `trade_features`, labels, wallet/funding dims, featuring backfill queue
