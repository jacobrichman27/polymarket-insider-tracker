# Contract: Featured Enrichment Config and Health

**Feature**: `007-featured-enrichment`  
**Owns**: FR-015, research Decision 10–11

## Settings (conceptual names — exact env aliases in implement)

| Setting | Default | Notes |
| --- | --- | --- |
| `ARCHIVE_ENABLED` | false | Unchanged A0 |
| `ARCHIVE_FEATURING_ENABLED` | false | Requires archive on; starts featuring/enrichment workers |
| Notional cutoff | 5000 | Versioned; clarify-locked provisional |
| Enrichment caps | 60s / 8 RPC / 10 pages or 15s | Versioned; revise after ops data |
| Classifier-control rate | provisional 0.1% | Versioned; bounded |
| Version stamps | featuring/enrichment/fingerprint/feature | Bump on definition change |

Secret-bearing URLs/credentials follow existing redaction rules. No execution/order settings.

## Dry-run

When dry-run + archive + featuring: enrichment/feature durable writes **MAY** proceed; Discord/Telegram delivery remains suppressed; must not poison real-delivery dedup (003/005 rules).

## Health

- `trade_archive` SLOs remain insert/owed/backlog (003/005). Enrichment lag alone MUST NOT mark tape `down`.
- When `ARCHIVE_FEATURING_ENABLED`, register diagnostic component `featured_enrichment` (`up` / `degraded` only — never alone fails `/ready`). Degrade on recent enrichment-loop / featuring-enqueue errors, chronic markets `failed`, or high `skipped_budget` share (provisional ratios in `enrichment_health.py`).
- Prometheus: `polymarket_enrichment_*`, `polymarket_featuring_enqueue_total`, `polymarket_featuring_reason_total`, `polymarket_signed_flow_*`, insert-time `polymarket_tape_anomaly_*` / lag / notional / price histograms, plus existing tape/repair/ingest metrics. Operator red-flag catalog: [`docs/collection-honesty-monitoring.md`](../../../docs/collection-honesty-monitoring.md).
- Cohort honesty audits (receipt vocabulary, FP collision, published signed-flow KPI sample) remain deferred A-001–A-017 — metrics do not replace them.
- Assessment persist failure MUST NOT block authorized alerts (constitution IV), including when featuring is enabled.

## Execution surface

Docs/config/tests MUST offer no place/cancel/order paths (extend A0/A1 no-execution tests).
