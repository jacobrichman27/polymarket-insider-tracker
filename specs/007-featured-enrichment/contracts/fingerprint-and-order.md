# Contract: Fingerprint and Order-As-Of

**Feature**: `007-featured-enrichment`  
**Owns**: FR-009, FR-010

## Fingerprint

| Kind | Key (conceptual) | When |
| --- | --- | --- |
| Strong | `(transaction_hash, token_id, log_index)` when locator present | Receipt `ok`/`partial` with log_index |
| Weak | `(transaction_hash, token_id, price, size)` canonicalized | Otherwise |

**Weak canonicalization (`b.v2+`):** lowercase `transaction_hash`; strip `token_id`; `price` and `size_shares` as fixed-scale decimals (8 places each). Fail closed if weak path lacks price/size. Never include `side` or `proxy_wallet`. Multi-maker sweeps are separate fingerprints per slice price/size; use `assess_weak_collision` (observation_count > 2 or same_side_max > 1) as a collision KPI signal—not Core truth.

Persist `fill_fingerprint` + `fingerprint_version`. Fingerprint ≠ `observation_id`.

### Primary-analysis gate

Fingerprint-dependent market aggregates (match-once volume, λ inputs, burst, fingerprint-once counts) are **not** primary-analysis-ready until rematerialized under the locked `fingerprint_version`. Sensitivity strata may use weak keys if explicitly labeled.

## Order-as-of

Order-dependent derived fields (burst origin, entry rank, same-second “before this trade”, convention canonical-leg when ties remain) MUST record:

| Contract | Meaning |
| --- | --- |
| `live_as_of` | Locators known at feature decision time only |
| `fully_enriched` | Rematerialize after receipts with locators then present |

### Immutability

Do **not** overwrite a frozen `live_as_of` feature row in place when a peer later gains locators. Rematerialize under a new `feature_version` and/or `fully_enriched`.

Rejected: claiming rematerialize-from-warm always equals live; sorting by ingest arrival alone while claiming on-chain total order.
