# Capacity burn-in receipt (Phase A0)

**Recorded**: 2026-11-25  
**Host**: local macOS Docker Compose (Postgres 15 + Redis 7) + dry-run tracker  
**Config**: `ARCHIVE_ENABLED=true`, `ARCHIVE_RAW_RETENTION=true`, `--dry-run --health-port 8088`  
**Nature**: Operator live run; append-only evidence for G-043 sizing revision and completeness under load. Not a claim of gap-free production.

## Window

| Field | Value |
| --- | --- |
| `archive_start_at` | 2026-11-23 04:00:55.516137+00 |
| Newest `observed_at` (at measurement) | 2026-11-25 01:43:56+00 |
| Wall span | ~45.72 h (~1 d 21 h) |
| `trades` row count | ~1,543,367 |
| Database size | ~2572 MB (~2.57 GiB) |
| Approx DB bytes/row | ~1748 B (~1.75 KiB) |

## Derived sizing

| Metric | Measured | Prior plan band |
| --- | --- | --- |
| Rows/day (n / wall days) | ~**810k/day** | 5×10⁵–2×10⁶ |
| Bytes/row (DB all-in) | ~**1.75 KiB** | ~2.5–10 KiB raw-on (plan table); ~1 KiB example in Data.md disk formula |
| Revised 90-day primary sketch | 90 × 810k × 1.8 KiB × 2 (index) × 2 (safety) ≈ **~500 GiB** | Data.md example ~360 GiB |

Daily partitions observed with data: `trades_20261123` (~921k / 1507 MB), `trades_20261124` (~577k / 939 MB), `trades_20261125` (partial). Ahead-empty children present. **`polymarket_archive_partition_miss_total = 0`** at check time. Archive owed backlog **0**; `trade_archive` component stayed **up** while ingest readiness often failed.

## Completeness under load (same run)

| Signal | Observation |
| --- | --- |
| `/ready` | Frequently `false` with `ingestion` down (acquisition staleness > 60s) while monitor/archive work continued inside long cycles |
| Ingest state metric | Often `possible-data-loss` (4) |
| `ingest_gap_events` | **74** `horizon-expired` + **4** `restart-beyond-horizon` (at measurement) |
| Horizon gap duration | avg ~1578 s (~26 min); summed window lengths ~32.4 h (not a claim of zero rows in those walls—boundary incompleteness) |

**Interpretation:** Disk/partition provisioning for this growth rate is feasible on a machine with hundreds of GiB free. **Gap-free** all-participant archive **with the full monitor path on this laptop** was **not** achieved: poll cycles routinely exceeded the acquisition freshness bound and the 10-minute recovery horizon. That is capacity/throughput evidence for ops placement (always-on host) and/or a later engineering isolation of monitor latency from acquisition cadence—not a failure of the `trades` schema or partition helper.

## Commands used (reproducible snapshot)

```bash
curl -s http://127.0.0.1:8088/ready
curl -s http://127.0.0.1:8088/health
curl -s http://127.0.0.1:8088/metrics | rg 'polymarket_archive_|polymarket_ingest_state'
docker exec polymarket-postgres psql -U tracker -d polymarket_tracker -c "…"  # counts, sizes, gap aggregates as in session
```
