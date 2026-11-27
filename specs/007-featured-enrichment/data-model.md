# Data Model: Featured Enrichment (Phase B)

**Feature**: `specs/007-featured-enrichment`  
**Date**: 2026-11-25  
**Normative field tables**: root [`Data.md`](../../Data.md) §§1–6, Featuring, Enrichment, Retention. This document is the B **platform** implementation subset (statuses, dims, optional `trade_features` grain). Full §§1–6 **Core** / **Useful** catalog materialization is owned by proposed B.1/`010` and B.2/`011` (G-052/G-053)—not by FR-013 MAY alone.

## Entities

### FeaturingDecision (logical)

| Field | Notes |
| --- | --- |
| `observation_id` / `trade_ts` | Tape identity |
| `featuring_config_version` | Gate + cutoff version |
| `eligible` | bool |
| `reason` | e.g. below_notional, regime_unknown, regime_no_private_edge, classifier_control, eligible |
| `decided_at` | UTC |

### EnrichmentWorkItem (durable queue row or equivalent)

| Field | Notes |
| --- | --- |
| `work_id` | Surrogate |
| `observation_id`, `trade_ts` | Target fill |
| `enrichment_budget_version` | Caps version |
| `trigger` | `insert_time` / `regime_upgrade` / `retry` / `classifier_control`. Rematerialize uses `retry` via `FeaturingEnrichmentRepository.enqueue_rematerialize` (unique with budget version, so insert_time completion does not block rematerialize). |
| `status` | `pending` / `running` / `completed` / `abandoned` |
| `enqueued_at`, `started_at`, `finished_at` | UTC |
| `last_error` | nullable, non-secret |

### Trades row extensions (hot/warm as Data.md Retain)

Add/confirm columns (names may match Data.md):

| Column | Purpose |
| --- | --- |
| `receipt_status`, locator fields, `onchain_direction`, counterparties, fees | Receipt arm |
| `gamma_enrichment_status` | Markets/Gamma arm for feature pass |
| `funding_lookup_status` / funding refs | Funding arm |
| `wallet_hydrate_status` | Hydrate arm |
| `fill_fingerprint`, `fingerprint_version` | Match-once key |
| `featuring_*` / enrichment attempt markers as needed | Ops/debug |

Null enriched fields allowed only when status explains them.

### TradeFeatures (optional)

| Field | Notes |
| --- | --- |
| `observation_id`, `trade_ts` | FK to tape |
| `feature_version` | Definition version |
| `order_as_of_contract` | `live_as_of` \| `fully_enriched` |
| `enrichment_budget_version`, `fingerprint_version` | Provenance |
| Derived section 2–6 columns | Convenience snapshot only |
| `materialized_at` | UTC |

**Forbidden:** section 7–8 label fields on this row.

### Wallets (versioned)

Append-on-change or event-cached wallet hydrate summary: identity, hydrate status, lifetime aggregates keyed for rematerialize by event time before `trade_ts`.

### ProxyFunding (versioned)

Dune-scheduled + Transfer-log writers per Data.md; snapshot vs event-time rematerialize rules unchanged.

## Relationships

- `trades` 1—0..1 featured enrichment completion per budget version (work item).
- `trades` 1—0..N `trade_features` across feature/order-as-of versions.
- Regime for gate: join A1 `markets` snapshot (`known_at` ≤ `trade_ts`); B does not rewrite trades knowability.
- Fingerprint groups multiple `trades` observations into one match for market aggregates.

## State transitions

### EnrichmentWorkItem

`pending` → `running` → `completed` | `abandoned`  
Retries may return `pending` under versioned policy while still hot.

### Arm statuses (per Data.md)

`not_attempted` → `pending` → `ok` | `partial` | `failed` | `skipped_budget` | `miss` (as applicable)

## Validation rules

- Featuring eligibility: regime `private_edge_possible` (legacy `private_settlement_possible` / `private_factor_possible` still eligible) AND notional ≥ cutoff (except classifier-control path).
- Shared arm reuse: receipt keyed by tx/fingerprint; funding/hydrate by proxy/wallet (FR-017).
- `live_as_of` feature rows immutable in place when peer locators arrive later.
- Hot backfill only for fills still inside hot retention window.

## Migration notes

- New Alembic revision `008_featured_enrichment` (exact id in implement).
- Upgrade + downgrade on disposable Postgres only for gates; do not point destructive tests at live burn-in DB without consent.
- Expand daily `trades` partitions as needed for new columns (Postgres partition-aware ALTER strategy in implement).
