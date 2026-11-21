# Data Model: Research Trade Archive (Phase A0)

**Feature**: `specs/005-research-trade-archive`  
**Date**: 2026-11-18  
**Normative research field tables**: root [`Data.md`](../../Data.md) §1 and Durable gap schema. This document is the A0 implementation subset.

## Entities

### TradeObservation (in-memory bus payload)

Extends today’s slice-001 observation for archive-enabled delivery.

| Field | Type | Notes |
| --- | --- | --- |
| `event` | `TradeEvent` | Existing monitor DTO |
| `identity` | `str` (64-hex) | Slice-001 observation identity → `observation_id` |
| `provider_timestamp` | epoch / datetime | Boundary score |
| `outcome_resolution` | existing enum/struct | Unchanged |
| `raw_row` / `raw_row_json` | mapping or UTF-8 JSON | Provider payload; required when archive + raw retention on |
| `observed_at` | timestamptz | Collector-first-seen (UTC) |

Validation: identity-bearing fields already enforced by `trade_rows` parse; archive writer must refuse insert without identity or trade_ts.

### TradesTapeRow (`trades`)

Partitioned fact table. Primary key `(trade_ts, observation_id)`.

#### Identity and time (required)

| Column | Type | Rules |
| --- | --- | --- |
| `trade_ts` | `timestamptz` | Partition key; from API timestamp (block time) |
| `observation_id` | `char(64)` | Exact slice-001 identity; never redefined |
| `observed_at` | `timestamptz` | Collector clock UTC |
| `archive_start_at` | `timestamptz` | Deployment continuous-archive start (from collector state) |
| `source_id` | `text` | Ingest source namespace (same as Redis boundary) |

#### API / cheap warm fields (A0)

| Column | Type | Rules |
| --- | --- | --- |
| `transaction_hash` | `text` | Required |
| `proxy_wallet` | `text` | Required |
| `condition_id` | `text` | Required |
| `token_id` | `text` | Required (API asset) |
| `outcome` | `text` null | Raw API; may be empty |
| `outcome_index` | `int` null | Raw API; may be 999 |
| `side` | `text` | BUY/SELL |
| `price` | `numeric` | 0–1 |
| `size_shares` | `numeric` | API size |
| `notional_usdc` | `numeric` | size × price (cheap derived) |
| `source` | `text` | Endpoint/table enum/string |
| `neg_risk` | `bool` null | If present on API/cheap path; else null |

#### Status defaults (A0; enrichment deferred)

| Column | Type | A0 default |
| --- | --- | --- |
| `outcome_repair_status` | `text` | `not_attempted`, or `not_needed` when API label already usable |
| `outcome_repaired` | `text` null | null until A1 |
| `outcome_index_repaired` | `int` null | null until A1 |
| `receipt_status` | `text` | `not_attempted` |
| `info_knowability_regime` | `text` null | `unknown` allowed / stamped when classification absent |
| `knowability_label_source` | `text` null | e.g. `unknown` |

#### Hot-only Core raw

| Column | Type | Rules |
| --- | --- | --- |
| `raw_row_json` | `jsonb` null | Required when `ARCHIVE_RAW_RETENTION=true`; null only if versioned cost flag amends Core |

#### Explicitly omitted in A0

- `fill_fingerprint` / `fingerprint_version`
- Stored windowed `data_complete`
- Chain locator / fee / enrichment result columns (`block_number`, `log_index`, `onchain_direction`, `fee_usdc`, `counterparty_wallets`, `fills_in_tx`, `exchange_version`, …) — **deferred to Phase B migration**. A0 keeps `receipt_status='not_attempted'` only as a status default on the warm row; B adds locator/fee columns and may UPDATE in place. Locked 2026-11-18 (analyze remediation U2): do not reserve a large null-column set in A0.

#### Indexes

- PK `(trade_ts, observation_id)`
- `(condition_id, trade_ts)`
- `(proxy_wallet, trade_ts)`
- `(transaction_hash, trade_ts)`

#### Partitioning

- Parent RANGE on `trade_ts`
- Daily UTC child partitions
- Pre-create ≥7 days ahead; writer fails closed (observable) if target partition missing
- Interim ops: retain ~90 days on primary then **detach** (not silent DELETE)

### IngestGapEvent (`ingest_gap_events`)

| Column | Type | Rules |
| --- | --- | --- |
| `gap_id` | UUID / bigserial | PK |
| `source_id` | `text` | Required |
| `class` | `text` | `ingest_loss` \| `write_failure` |
| `reason` | `text` | ingest: `horizon-expired` \| `restart-beyond-horizon` \| `continuity-mismatch`; write: `archive_insert_failed` \| `archive_insert_abandoned` |
| `from_time` | `timestamptz` | Required |
| `to_time` | `timestamptz` null | Interval end or null/point |
| `observation_id` | `char(64)` null | Required for write_failure when known |
| `pages_examined` | `int` null | From Redis loss JSON when present |
| `detected_at` | `timestamptz` | Required |
| `recorded_at` | `timestamptz` | Required |
| `resolved_at` | `timestamptz` null | Set on resolve/abandon terminalization |
| `status` | `text` | `open` \| `resolved` \| `abandoned` |
| `redis_payload` | `jsonb` null | Optional verbatim ingest_loss copy |
| `detail` | `jsonb` null | Redacted write-failure diagnostics |

**Uniqueness:**
- `ingest_loss`: unique enough to survive Redis re-trim (e.g. `(source_id, class, reason, from_time, to_time, detected_at)` or payload hash)
- `write_failure`: one open row per `(source_id, observation_id)` (upsert on fail; resolve/abandon updates)

**State transitions (`write_failure`):**
```text
(none) --first fail--> open(archive_insert_failed)
open --insert success--> resolved
open --unreachable/exhaust--> abandoned(archive_insert_abandoned)
```

**State transitions (`ingest_loss`):**
```text
Redis loss push --> open (or upsert)
gap closed without loss --> resolved (when 001 closes without recording permanent loss)
horizon/permanent path --> remains research-visible (aligned with 001 loss durability)
```

### ArchiveCollectorState

Singleton (or keyed by `source_id`) durable row:

| Column | Type | Rules |
| --- | --- | --- |
| `source_id` | `text` | PK / unique |
| `archive_start_at` | `timestamptz` | Set once on first successful archive-enabled collection |
| `raw_retention` | `bool` | Effective at start (audit) |
| `updated_at` | `timestamptz` | Last touch |

Silent overwrite of `archive_start_at` is forbidden; explicit operator migration required to change.

### RiskAssessment (unchanged)

Remains sparse monitor evidence. Must never substitute for `trades`.

## Relationships

```text
TradeObservation --insert--> TradesTapeRow
TradeObservation --on fail--> IngestGapEvent(write_failure)
ObservationBoundary loss-events --copy--> IngestGapEvent(ingest_loss)
ArchiveCollectorState --stamps--> TradesTapeRow.archive_start_at
TradesTapeRow ≉ RiskAssessment (optional later join by observation_id; not required for A0)
```

## Capacity (provisional)

See [research.md](research.md) Decision 8 and `Data.md` Provisional capacity. Disk budget formula:

`days_on_primary × rows/day × bytes/row × (1 + index_factor) × safety` with safety ≥ 2.
