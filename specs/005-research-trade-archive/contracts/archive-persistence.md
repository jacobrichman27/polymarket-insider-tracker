# Contract: Archive Persistence (A0)

**Feature**: `specs/005-research-trade-archive`  
**Date**: 2026-11-18  
**Schema**: [data-model.md](../data-model.md) · normative field intent in root [`Data.md`](../../../Data.md)

## Trades insert

- **API**: Archive writer `write(observation) -> ArchiveWriteResult`
- **Success**: row durable under `(trade_ts, observation_id)` (insert or idempotent conflict no-op that leaves equivalent fact)
- **Failure**: raise/return failure without claiming durability; caller must not `record_identity`
- **Blocking prohibitions**: must not await Gamma, knowability model, Jev, featuring, or labels
- **Raw**: when `ARCHIVE_RAW_RETENTION=true` (default with archive on), `raw_row_json` MUST be stored; silent drop forbidden

## Idempotency

Re-delivery after crash or retry MUST NOT create a second logical fill. Conflict path is success for retain authorization.

## Gap ledger

### Ingest loss copy

On Redis `loss-events` push (or equivalent boundary write that appends a loss), upsert durable `ingest_gap_events` row with `class=ingest_loss` and 001 reason. Postgres outlives Redis trim (50).

### Write failure

| Event | Ledger action |
| --- | --- |
| First Archive fail for identity | Upsert `open` / `archive_insert_failed` |
| Later retry fail | Update `detail` (retry count, error class); keep `open` |
| Insert success | `resolved` + `resolved_at` |
| Unreachable / exhaust | `abandoned` / `archive_insert_abandoned` |

## Completeness (A0)

A0 does **not** store per-row `data_complete`. Downstream derivation MUST treat open/abandoned write failures and open ingest losses as spoiling intersecting windows; resolved write failures stop spoiling once the trades row exists.

## Collector state

First successful archive-enabled collection for a `source_id` persists `archive_start_at`. Subsequent starts reuse it. Overwrite requires explicit operator procedure documented in quickstart/migration notes.

## Capacity obligations

Deployment MUST provision disk per plan provisional budget, pre-create partitions (≥7 days ahead), and expose:
- **In-process:** missing-partition / partition-miss fail-closed signal; insert-rate metric; owed backlog → `trade_archive`
- **Ops/host:** disk ≥70% of documented budget (runbook; not required as an in-process disk poller)

Detach older-than-interim partitions; do not silent-delete fills.

## Dry-run

When archive writing is enabled, dry-run MUST still insert into `trades` and update the gap ledger. Dry-run MUST NOT send real Discord/Telegram messages or write delivery-dedup keys (slice 003).
