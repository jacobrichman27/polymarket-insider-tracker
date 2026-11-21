# Contract: Observation Fan-Out Delivery (A0)

**Feature**: `specs/005-research-trade-archive`  
**Date**: 2026-11-18  
**Boundary owner**: slice 001 [`observation-boundary.md`](../../001-supported-trade-ingestion/contracts/observation-boundary.md)  
**Implementer**: slice 005 (this contract restates consumable runtime obligations; it does not redefine identity retention)

## Modes

| Mode | Config | Delivery |
| --- | --- | --- |
| Monitor-only | `ARCHIVE_ENABLED=false` (default) | Legacy `on_trade(TradeEvent)`; retain after Monitor returns |
| Archive-enabled | `ARCHIVE_ENABLED=true` | Ordered fan-out; policy **(a)** |

Enabling archive without an Archive consumer is a wiring error (must not silently degrade to monitor-only).

## Archive-enabled sequence (normative)

Per observation, oldest-first among candidates:

1. Build full `TradeObservation` (event + identity + provenance + raw when raw retention on).
2. **Archive.write(observation)** → durable idempotent insert.
3. If Archive ok → `record_identity` → count `EMITTED` for boundary credit.
4. If Archive fail → do **not** retain; open/update `write_failure`; keep owed; do **not** advance checkpoint past owed set.
5. **Monitor** still runs with `TradeEvent` (A0 deprecation adapter) whether Archive succeeded or failed.
6. Monitor exceptions: log/count only; never undo Archive or revoke identity.
7. Reserved future slot: protocol only; must not place orders.

## Checkpoint stall

`ObservationBoundary.advance` for a proven page MUST wait until every newly emitted archive-destined observation on that page is archive-credited (identity retained). Retry Archive with bounded backoff while owed. Reject advancing `T` to “keep moving” during outage.

## Crash cases (must be tested)

| Crash point | Expected restart behavior |
| --- | --- |
| After insert ok, before `record_identity` | Re-deliver; insert no-op; then retain |
| Before insert ok | Re-deliver while reachable; no retain until success |
| After retain, before page `advance` | Next proof suppresses duplicates via identity window |

## Isolation matrix

| Failure | Archive | Monitor | Identity |
| --- | --- | --- | --- |
| Archive fail | Recorded; retry/stall | Still invoked | Not retained |
| Monitor fail after Archive ok | Unchanged | Logged | Retained |
| Monitor fail and Archive never ok | N/A | Logged | Not retained |

## Retry backoff (provisional)

While owed and reachable: initial **250 ms**, exponential **×2**, cap **5 s** between attempts. Abandon is driven by reachability / recovery horizon, not a fixed attempt budget.

## Abandon

When an owed observation becomes unreachable from live acquisition / recovery horizon before durable insert: set `write_failure` → `abandoned` / `archive_insert_abandoned`; alarm; denominators unrestored for that identity. Do not claim completeness.

## Dry-run

Archive inserts still run under dry-run when archive writing is enabled; only notification delivery is suppressed.
