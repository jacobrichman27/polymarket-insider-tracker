# Contract: Durable Observation Boundary

## Purpose

Defines the durable state that makes overlapping acquisition safe, the proof required before the
boundary advances, the recovery path, the possible-data-loss state, and the crash semantics. It is
implemented by `ingestor/observation_boundary.py` and driven by `ingestor/trade_poller.py`.

**Amendment (2026-11-18, G-036–G-038 / G-037):** when archive writing is enabled, this contract also
owns observation **fan-out**, **identity-retention authorization** under recovery policy **(a)**, and
**checkpoint stall** until archive-durable success. Normative research schema lives in root
[`Data.md`](../../../Data.md); slice `005-research-trade-archive` implements the archive writer and
consumes this amended contract. Slice 005 must not redefine identity retention or invent a parallel
proof model.

## Keys

All keys share the prefix `polymarket:ingest:<source-id>:` where `source-id` is the first 12 hex
characters of `sha256("<trades_url>|<coverage>")`. Changing the URL or the coverage mode therefore
starts a fresh boundary with first-start semantics rather than mixing identity spaces.

| Key | Type | Content |
|---|---|---|
| `checkpoint` | hash | `schema_version=2`, `boundary_time`, `emission_floor`, `boundary_origin`, `written_at`, `coverage`, `last_request_end` |
| `identities` | sorted set | member = observation identity, score = provider timestamp |
| `loss-events` | list | newest-first JSON loss events, trimmed to 50 |

Every boundary advance watches and validates all three key types, then writes `checkpoint`, the new
`identities` members, the `identities` trim, and any `loss-events` push in one `MULTI`/`EXEC`
transaction. A failed validation or write leaves the previous checkpoint intact and the cycle is
reported as a failure.

## Proof Before Advance

Given the durable boundary time `T` and the retained identity window `W`, and a cycle's parsed page
`P` (valid rows at or before the cycle cutoff only, padding included, sorted ascending by
`(timestamp, identity)`):

```text
oldest     = min(timestamp(row) for row in P)
reach      = oldest < T
expected   = { identity ∈ W : score(identity) > oldest }
continuity = expected ⊆ identities(P)
proven     = reach and continuity
```

- `P` empty: not proven, not a loss; `last_success_at` updates, nothing is emitted, `T` unchanged.
- `proven`: emit new observations, retain their identities, set `T' = max(timestamp(row) for eligible
  rows)`, trim identities with score `< T' - horizon`, write `boundary_origin = proven`.
- not `proven`: perform exactly one recovery request (`offset=10000`), merge by identity, and evaluate
  again. If still not proven, open a gap `[T, oldest)` and enter `possible-data-loss`.

Page length is never an input to the proof.

Rows newer than the cycle cutoff are counted as `deferred:future-cycle` and excluded from proof,
emission, identity retention, and `T'`. They are eligible for reacquisition in a later cycle. Thus the
durable `T` is a complete-through claim, not a newest-seen watermark.

## Candidate Selection and Emission

- Candidate rows are valid rows with
  `timestamp >= max(newest_accepted - horizon, emission_floor)`; older rows are `padding`.
- `emission_floor` is set to the newest timestamp on first start and re-anchor and is preserved on
  normal proven advances. It therefore cannot drift when a sparse identity window is trimmed.
- A candidate whose identity is in `W` is a `duplicate`; otherwise it is emitted oldest-first as a
  full `TradeObservation` (event + identity + provenance + raw payload when captured) through the
  delivery step in [Delivery and identity retention](#delivery-and-identity-retention-amendment-2026-11-18).
- Multiple rows sharing a transaction hash are distinct observations unless their full identity tuple is
  equal; exact repeats within one page are suppressed once and counted as duplicates.

**Emission credit (`EMITTED`) and identity retention are not the same as “callback returned.”** See
the amendment section. Monitor-only (archive disabled) preserves the historical single-consumer path
with the deprecation adapter below; archive-enabled runs must not use retain-always-after-callback.

## Possible-Data-Loss State

- The durable `T` is frozen; the gap interval and `pages_examined` are held in memory.
- A provisional boundary `T_p` (newest accepted timestamp of the last page) is used to prove
  continuity between consecutive pages with the same rule, so every unproven interval becomes its own
  gap record.
- New observations keep flowing with identity de-duplication; `W` keeps growing behind `T_p` and is
  trimmed relative to `T_p`.
- Exit paths:
  - a later page proves against the frozen `T`: the gap closes without a loss event and normal advance
    resumes;
  - `T` becomes older than the horizon: every open gap is written as a loss event with reason
    `horizon-expired`, `T' = T_p`, `boundary_origin = re-anchored`, state returns to `running`.

## First Start and Restart

| Situation | Behavior |
|---|---|
| No checkpoint, or a checkpoint whose `coverage` differs from the configuration | First start: fetch one page, `T = newest accepted`, retain identities within the horizon, emit nothing, `boundary_origin = first-start` |
| Checkpoint with a schema version other than `2` | Terminal configuration error; the poller enters `failed` and touches nothing; version 1 cannot reconstruct the stable emission floor or revised identity space |
| Checkpoint age `now - T <= horizon` | Reload `W` from Redis, then run the normal proof; if reachable, emitted rows are exactly the candidates not in `W`; otherwise enter `possible-data-loss` |
| Checkpoint age `now - T > horizon` | Write a loss event `[T, newest accepted]` with reason `restart-beyond-horizon`, re-anchor without emission |

The reachable depth is 20,000 rows, so the 10-minute horizon does not guarantee 10-minute recovery. A
restart inside the horizon can still fail proof after roughly five to seven minutes at the observed
rates; that produces the possible-data-loss path above, not a silent skip.

## Crash Semantics

### Monitor-only (archive writing disabled)

- The identity of an observation is written after the Monitor consumer returns (success or logged
  failure), in emission order—the historical single-callback behavior, retained for deprecation.
- The checkpoint advances after the whole proven page is delivered under that rule.
- A crash between Monitor return and identity write re-delivers at most that one observation on
  restart. The scorer's existing deduplication window remains a second guard for alert side effects.
- A crash between identity writes and the checkpoint write leaves `T` at its previous value; the next
  proof still holds because the identities were retained, and the candidates are suppressed as
  duplicates.

### Archive-enabled (policy (a) — locked 2026-11-18)

- Identity is written **only after** Archive reports durable insert success for that observation
  (idempotent on `(trade_ts, observation_id)`), in emission order.
- The checkpoint advances only after the whole proven page is **archive-credited** (every newly
  emitted archive-destined observation on that page has a retained identity). See checkpoint stall.
- A crash **after** Archive insert success and **before** identity write: the row is durable in
  Postgres; identity is missing in Redis. Restart may re-deliver; Archive insert is an idempotent
  no-op; then identity is retained. No silent loss of the fill.
- A crash **before** Archive insert success: identity is not retained; restart re-delivers while the
  observation remains reachable from acquisition / in-memory retry. No silent “handled” credit.
- A crash between identity writes and the checkpoint write: same as monitor-only—`T` stays; retained
  identities suppress duplicates on the next proof.

**Rejected:** retain identity after Monitor returns when Archive has not succeeded; advance `T` past
observations that are not yet archive-durable; marker-only advance with no re-delivery path.

## Loss Event

```json
{"from_time": 1788983716, "to_time": 1788983935, "reason": "horizon-expired",
 "detected_at": 1788983940, "recorded_at": 1788984320, "pages_examined": 2}
```

**Ingest-loss reasons** (Redis `loss-events`, unchanged): `horizon-expired`,
`restart-beyond-horizon`, `continuity-mismatch`. Events are logged at `ERROR` when written, exposed
in status (`loss_events`, newest five), and counted by the metric
`polymarket_ingest_loss_events_total{reason}`.

**Write-failure** (archive insert failed / abandoned) is **not** overloaded onto those three ingest
reasons. Durable research ledger rows use class `write_failure` in Postgres `ingest_gap_events`
(schema owned with slice 005 / `Data.md`). This contract authorizes that vocabulary so it is not an
undeclared side channel; Redis may mirror write-failure for ops, but Postgres is authoritative for
research completeness. Permanent unreachable fills under policy (a) still set
`data_complete=false` for affected windows and alarm per `Data.md`.

## Delivery and identity retention (amendment 2026-11-18)

### Modes

| Mode | When | Delivery shape |
|---|---|---|
| Monitor-only | Archive writing disabled | Legacy `on_trade(TradeEvent)` (or Monitor-only fan-out). Identity retention after Monitor returns (historical). |
| Archive-enabled | Archive writing enabled | Ordered fan-out of `TradeObservation` per observation. Policy **(a)** below. |

Enabling archive writing without Archive in the fan-out is a configuration / wiring error: it must
not silently run as monitor-only.

### Fan-out order (archive-enabled)

Per observation, fixed order:

1. **Archive** (required) — idempotent durable `trades` insert (and Core hot `raw_row_json` when
   required by `Data.md`).
2. **Monitor** (optional) — detect / score / alert path; receives at least `TradeEvent`, preferably
   full `TradeObservation`. Must not assume the row is on the tape unless Archive already succeeded.
3. **Future decision/execution** — reserved interface slot only; must not run order-placement code
   under this slice.

**Who authorizes identity retain and `EMITTED`:** this delivery step (poller / boundary driver)—**not**
the Monitor. Monitor success or failure never authorizes or revokes identity retention.

### Policy (a) — locked default

- Successful Archive durable insert authorizes `record_identity` and emission credit (`EMITTED`) for
  that observation.
- Archive failure: **do not** retain identity; **do not** treat as `EMITTED` for boundary credit;
  retry with bounded backoff; observation remains eligible for re-delivery while reachable.
- Monitor is **still invoked** after Archive failure with the in-memory observation (failure
  isolation); Monitor must not assume tape durability.
- Monitor failure after Archive success: log / count only; **must not** undo Archive or revoke
  identity.

Policy **(b)** (advance with durable outbox + reconciler) is **not** the A0 default. Switching
requires a later versioned amendment of this contract.

### Checkpoint stall (archive-enabled, policy (a))

Acquisition proof (`proven` / recovery / possible-data-loss) is unchanged. **Advancing the durable
complete-through checkpoint `T`** additionally requires that every newly emitted archive-destined
observation for that page has been archive-credited (identity retained under policy (a)).

While any such observation is owed (delivered to Archive but not yet durable / not retained):

- **Do not** advance `T` past that observation.
- Retry Archive insert with bounded backoff.
- Surface archive / collection health as degraded then down per the dual-use tape SLOs in `Data.md`
  / slice 003 health amendment (provisional: degraded after 30s owed or a failure in 60s; down /
  fail ready after 5 minutes owed or 5 minutes of failed attempts; quiet markets stay up).
- **Rejected:** advancing `T` anyway during a long Archive outage to “keep the poller moving.”

If, despite stalling, a fill becomes unreachable before it is ever inserted, record durable
write-failure evidence, set `data_complete=false` for affected windows, and alarm. Denominators are
not restored for that identity.

### Exception isolation matrix (archive-enabled, policy (a))

| Failure | Archive | Monitor | Identity / `EMITTED` |
|---|---|---|---|
| Archive raises / insert fails | Failure recorded; retry / stall | Still invoked (in-memory) | Do not retain; not emitted for boundary credit |
| Monitor raises after Archive success | Unchanged | Logged / counted; must not undo Archive | Retain; emitted |
| Monitor raises and Archive never succeeded | N/A | Logged / counted | Do not retain |

Constitution IV (assessment persist must not block alert dispatch) remains internal to Monitor and
orthogonal to Archive retain.

### Deprecation adapter

`TradePoller` may still accept legacy `on_trade: TradeCallback` by wrapping it as the Monitor
consumer behind the fan-out driver. New wiring passes explicit Archive + Monitor consumers.
Legacy single-callback mode without Archive is **monitor-only** (archive disabled)—not an accidental
skip of the tape when archive writing is enabled.

### Sequence diagrams (normative)

Happy path, Archive fail, Monitor fail after Archive ok, and crash between Archive ok and
`record_identity` are specified in [`Data.md`](../../../Data.md) under **Observation fan-out
contract**. Implementations and tests MUST match those sequences under policy (a).

## Real and Fake Parity

The operations used by this contract (`HSET`/`HGETALL`, `ZADD`, `ZRANGEBYSCORE`, `ZREMRANGEBYSCORE`,
`ZCARD`, `LPUSH`/`LTRIM`/`LRANGE`, and a transactional pipeline that contains all of them) are added as
scenarios to `tests/integration/test_redis_contract.py`, which runs against `fakeredis` in every unit run
and against the real loopback Redis in the `services` profile. The in-memory mirror of `W` must equal
the Redis sorted set after every cycle in tests. `FLUSHDB` is never used; every scenario writes inside a
unique namespace it deletes.
