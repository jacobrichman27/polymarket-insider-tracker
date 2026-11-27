# Collection honesty monitoring

Operator catalog of **plausible red flags** for the research trade archive. Normative field/KPI rules live in [`Data.md`](../Data.md); this document maps them to **signals**, **planes**, and **isolation** so enrichment honesty never fails tape readiness or blocks alerts (constitution IV).

**Planes**

| Plane | Surface | Use |
| --- | --- | --- |
| Ready | `GET /ready` | Process claims collection health; only component `down` fails it |
| Health | `GET /health` | `up` / `degraded` / `down` per component |
| Metrics | `GET /metrics` (Prometheus) | Rates, histograms, backlog ages — scrape + alert externally |
| Durable | Postgres ledgers / statuses | Forensics and cohort audits (007 deferred A-001–A-017) |
| Risk alerts | Discord/Telegram | Score-gated only — **not** tape/enrichment paging |

Enrichment / repair diagnostics may be `degraded` on `/health` while `/ready` stays true. They **must not** alone mark `trade_archive` `down`.

Post-run burn-in analysis (early featuring cutoff **$500**, production lens **$5k**): [`archive-burnin-analysis.md`](archive-burnin-analysis.md) + `scripts/archive_burnin_report.py`.

---

## Red-flag catalog (provisional thresholds — version after ops data)

### Ingest / boundary (001)

| Red flag | Why plausible | Signal today | Action |
| --- | --- | --- | --- |
| Sustained `horizon-expired` / page unproven | Laptop+monitor / slow consumers | `polymarket_ingest_loss_events_total{reason}`; durable `ingest_gap_events` | Page ops; always-on host / isolate monitor load |
| Acquisition freshness >60s while process up | Size-anomaly CLOB miss retries share the poller loop | `/health` ingestion `down`; CLOB `get_market` warn storms | Set `ARCHIVE_COLLECT_PRIORITY=true` for tape burn-in; hot-path miss coalesce + zero retries (process isolation still deferred) |
| Provider lag spike | API slowdown | `ingest_provider_lag_seconds` | Degrade investigation; do not advance past unproven pages |
| Boundary stall with empty market | Misread quiet vs stuck | `ingest_boundary_timestamp_seconds` + quiet exemption | Confirm with tape insert rate |

### Tape persist (A0 / `trade_archive`)

| Red flag | Why plausible | Signal today | Action |
| --- | --- | --- | --- |
| Owed backlog >30s / >5min | Insert failures / stall under policy (a) | `trade_archive` health; `archive_oldest_owed_age_seconds` | Ready fails only at **down**; restore or abandon+alarm |
| Partition miss | Ahead-create failed | `archive_partition_miss_total` | Page immediately — fail-closed inserts |
| Write abandon rate | Exhausted re-emit horizon | `archive_write_failures_total{reason=abandoned}` | Permanent hole; `data_complete` honesty |
| Insert rate 2× sizing plan | Capacity runaway | `archive_insert_rate_total` | Disk/autovacuum runbook (host disk ≥70% ops-only) |

### Unexpected input / distribution (shape drift)

These catch **weird tape** before analysis trusts windows. Prefer rate/ratio alerts vs absolute counts. Provisional alert ideas in italics.

| Indicator | Why it matters | Metric | Provisional alert |
| --- | --- | --- | --- |
| Thin API outcomes (`999`/empty) | Repair load / label poison | `tape_anomaly_total{kind=thin_outcome}` | *Share of inserts > baseline +20pp for 1h* |
| Price outside \[0,1\] | Schema/provider bug | `tape_anomaly_total{kind=price_out_of_range}` | *Any sustained >0* |
| Side not BUY/SELL | Enum drift | `tape_anomaly_total{kind=unexpected_side}` | *Any* |
| Non-positive size/notional | Bad parse / dust abuse | `tape_anomaly_total{kind=nonpositive_size_or_notional}` | *Rate >0.1% of inserts* |
| Missing tx/wallet on row | Identity break | `tape_anomaly_total{kind=missing_identity_fields}` | *Any* |
| Future `trade_ts` | Clock skew / bad provider time | `tape_anomaly_total{kind=future_trade_ts}` | *Any sustained* |
| Stale fill (>1h lag at insert) | Boundary stall / backlog | `tape_anomaly_total{kind=stale_trade_ts}` + lag histogram | *p95 lag >15m or stale share >1%* |
| Missing Core `raw_row` while retention on | Silent Core drop | `tape_anomaly_total{kind=missing_raw_row}` | *Any when raw-on* |
| Ingest lag distribution | Acquisition health | `tape_ingest_lag_seconds` | *p95 vs 72h baseline* |
| Notional mix shift | Featuring/$5k cohort change; wash/spam | `tape_notional_usdc` | *Share ≥$5k doubles; or <$1 share explodes* |
| Price pile at 0/1 | Resolution print flood / bad book | `tape_price` | *Share in {0,1} bins spikes* |
| Featuring reason mix | Regime/notional policy drift | `featuring_reason_total{reason}` | *`unknown`/below_cutoff share jumps* |
| Duplicate:insert ratio | Replay storm / identity churn | `archive_inserts_total` | *duplicates ≫ inserts for 15m* |
| Receipt completed as `pending` | Stub / decode hang | `enrichment_unexpected_total{kind=receipt_still_pending}` | *After A-001: any on completed attempts* |
| Hydrate claimed `ok` | Stub / unverified Data-API walk | `enrichment_unexpected_total{kind=hydrate_ok_unverified}` | *Any until real walk lands; stubs must stay `pending`* |
| Unknown arm status string | Code/contract drift | `enrichment_unexpected_total{kind=markets_unknown_status}` | *Any* |
| Markets/Gamma status vs column | Arm key `markets` → `gamma_enrichment_status`; snapshot join is `partial` not Gamma `ok` | Arm counters + row column | *Treat `ok` as live refresh only* |

**Not yet scraped (add when cheap):** new-`condition_id`/day rate; same-`transaction_hash` observation fan-out histogram (multi-maker vs runaway); open `ingest_gap_events` gauge by class; `data_complete` busy-window rate; weak-FP collision rate (A-003); funding `miss`∧Transfer fail after Dune lag window.

### Outcome repair (A1)

| Red flag | Why plausible | Signal today | Action |
| --- | --- | --- | --- |
| Thin rows stuck `not_attempted` past lag | Repair worker down / Gamma | `outcome_repair` degraded; lag/unrepaired gauges | Fix repair; block Phase C primary until KPI ok |
| Unrepaired ratio > ceiling (~5%) | Token map holes | `outcome_repair_unrepaired_ratio` | Do not ship win/loss labels as Core |

### Featuring / enrichment platform (B / 007)

| Red flag | Why plausible | Signal | Action |
| --- | --- | --- | --- |
| Enrichment loop errors | RPC/API/DB faults | `featured_enrichment` degraded; `enrichment_loop_errors_total` | Investigate; tape ready holds |
| Featuring enqueue failures | Insert path fire-and-forget miss | `featuring_enqueue_total{result=error}` | Hot fills never enriched |
| Arm `failed` / chronic `skipped_budget` | Budget too tight / arm bugs | `enrichment_arm_status_total{arm,status}` | Raise budget version or fix arm; do not claim Core fields |
| Receipt stuck `pending` / fake vocabulary | Stub decode | Arm counters + deferred audit A-001 | No signed-flow Core overweight |
| Hydrate `ok` with empty lifetime facts | Dishonest stub | Arm status + A-013 audit | Treat as dualism breach; fix before B.1 Core |
| Funding `miss` / inexact first fund clustered | Dune lag + window Transfer | `funding_lookup_status` / `first_funding_exact` (row + future gauges) | No strong cluster on inexact |
| Signed-flow KPI unpublished | Cohort not audited | `signed_flow_kpi_published`; disagreement counters | λ / imbalance Useful only (`lambda_core_allowed`) |
| Weak fingerprint collision rate high | Multi-maker / fee aliases | Deferred A-003 export | Rematerialize / stratum; bump FP version if needed |
| Regime-upgrade backfill silent miss | Left-hot / worker stop | Featuring enqueue trigger labels | A-012 audit |

### Funding honesty (analysis contract — not “fix fiat”)

| Red flag | Why | Monitoring stance |
| --- | --- | --- |
| Clustering on bridge/`deposit` funders | Shared weak link | Fail closed: require `first_funding_exact` + uncommon funder in analysis; optional later known-bridge denylist metric |
| Claiming fiat vs crypto origin | Not on-chain | **Do not monitor as a product KPI** — out of scope |
| Dune lag miss on fresh featured wallets | Expected ~1h | `funding_lookup_status=miss` rate — expected spike, alarm only if Transfer also fails |

### Core / Useful field delivery (B.1 / B.2 — when specified)

| Red flag | Why | Stance |
| --- | --- | --- |
| Core coverage matrix row missing | Silent catalog hole | G-052 acceptance; ledger in `010` |
| Fake-complete hydrate/funding feeding Core snapshots | Overclaim | G-052 + arm honesty metrics above |

### Labels (C — future)

| Red flag | Stance |
| --- | --- |
| `label_schedule_*` overdue / skip bias | Phase C KPI — not wired yet |

---

## Isolation matrix (locked)

| Condition | `/ready` | `trade_archive` | Risk alerts |
| --- | --- | --- | --- |
| Tape insert down (owed SLO) | Fail | `down` | Still must not block authorized attempt |
| Outcome repair KPI breach | Hold | Unchanged | Unchanged |
| Featured enrichment degraded | Hold | Unchanged | Unchanged |
| Assessment persist fail | Hold | Unchanged | Dispatch still allowed |

---

## Implementation status

| Area | In-process now | Still deferred |
| --- | --- | --- |
| Ingest + tape | Metrics + `trade_archive` | Alertmanager rules; disk scrape |
| Outcome repair | Metrics + diagnostic component | Live burn-in cutover claim |
| Featured enrichment | Metrics + `featured_enrichment` diagnostic (2026-11-26); reason + unexpected counters | Cohort audits A-001–A-017; queue-depth SQL gauge; Alertmanager |
| Tape shape / lag | `tape_anomaly_*`, lag/notional/price histograms (2026-11-26) | Market/tx fan-out gauges; Alertmanager baselining |
| Gap ledger rates | Durable rows; ingest loss + `archive_gap_events_total` | Postgres open-gap gauges / `data_complete` export |
| Fingerprint / signed-flow publish | Helpers + disagreement counters when observed | Disposable-cohort KPI publish gate |
| B.1/B.2 field coverage | Gaps G-052/G-053 | Spec Kit `010`/`011` |

External alerting (PagerDuty/Alertmanager) is **ops wiring** on scraped metrics — not Discord risk alerts.
