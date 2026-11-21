# Contract: Archive Config and Tape Health (A0)

**Feature**: `specs/005-research-trade-archive`  
**Date**: 2026-11-18  
**Health owner**: slice 003 [`health-endpoints.md`](../../003-safe-observable-operation/contracts/health-endpoints.md)  
**Implementer**: slice 005 supplies signals and registers the component when enabled

## Configuration

| Setting | Env | Default | Meaning |
| --- | --- | --- | --- |
| Archive writing | `ARCHIVE_ENABLED` | `false` | Opt-in research tape + policy (a) delivery |
| Raw retention | `ARCHIVE_RAW_RETENTION` | `true` | Core hot raw on insert when archive on; off only via versioned cost amendment |
| (optional) retry bounds | `ARCHIVE_*` tunables | plan defaults | Bounded backoff for owed inserts |

`--config-check` MUST print a redacted summary including archive enabled/raw flags and MUST NOT print secrets. Migration note in README / `.env.example`: how to enable the tape and that default remains monitor-only.

When `ARCHIVE_ENABLED=true`, pipeline wiring MUST install Archive + Monitor fan-out (not retain-always single callback).

## Plane flags (documentation, not dormant trading)

Public docs MUST state: data plane (tape) ships; decision remains monitor scoring; execution is out of product. No order-placement settings.

## `trade_archive` health component

Registered **only** when `ARCHIVE_ENABLED=true`.

Signals (minimum):

- `oldest_owed_age_seconds` (from first archive-destined attempt for owed identities)
- `recent_insert_failure` (any failure in last 60s)
- `all_attempts_failed_window` (trailing 5 min with ≥1 attempt)
- quiet: no attempts and no owed → `up`

Map to 003 SLO table:

| Status | Condition |
| --- | --- |
| `up` | No owed >30s; no failure in 60s; or quiet |
| `degraded` | Failure in 60s OR owed in (30s, 5min) |
| `down` | Owed >5min OR all attempts failed for 5min with ≥1 attempt |

`/ready` fails only when this component (or other required components) is `down`.

## Constitution IV split

Assessment persist failure MUST NOT mark `trade_archive` down and MUST NOT block authorized alerts. Tape readiness is collection readiness, not alert suppression.

## Metrics (illustrative names)

- `polymarket_archive_inserts_total{result}`
- `polymarket_archive_owed_observations`
- `polymarket_archive_write_failures_total{reason}`
- `polymarket_archive_oldest_owed_age_seconds`

Exact metric names may follow existing Prometheus naming in `trade_poller` / health modules; contract requires the signals above to be observable.
