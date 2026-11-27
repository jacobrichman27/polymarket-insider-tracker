# Contract: Enrichment Budget and Arms

**Feature**: `007-featured-enrichment`  
**Owns**: FR-003–FR-006, FR-017

## Non-blocking

Enrichment runs asynchronously. Injected slowness MUST NOT stall Archive insert or poller emission.

## Arm order (highest value first)

1. Markets / Gamma (`gamma_enrichment_status`)
2. Receipt decode (`receipt_status`, locators, `onchain_direction`, counterparties when applicable)
3. Transfer-log funding on miss/top-up (`funding_lookup_status`)
4. Lifetime hydrate on miss (`wallet_hydrate_status`)

Reuse external results when a prior version already satisfies the arm; still record this pass’s status.

## Caps (provisional — revise after ops data)

| Cap | Starting point |
| --- | --- |
| Wall clock per attempt | ~60s (queue may retry while `pending`) |
| Polygon RPC calls | ~8 per featured trade attempt |
| Hydrate Data API | ~10 pages or ~15s, whichever first |

Record `enrichment_budget_version` whenever caps change. Cheap local work is not charged to RPC cap.

## Degrade order (over budget)

1. Skip/defer hydrate → `skipped_budget` / `pending`
2. Skip Transfer logs if prior funding exists; else `skipped_budget`
3. Skip receipt only as last resort → `receipt_status=skipped_budget`
4. Do **not** skip markets/Gamma for featured rows; on failure set `failed` and continue

## Status honesty

Null enriched fields are allowed only when status explains them (`not_attempted`, `pending`, `ok`, `partial`, `failed`, `skipped_budget`, `miss`, …).

## FR-017 hybrid reuse

- Featuring eligibility: per observation.
- Receipt arm: once per transaction / fingerprint grain; both featured legs share result.
- Funding / hydrate: once per proxy/wallet grain.
- Unfeatured opposite/small legs: counterparties via tape fingerprint pair-assist without requiring featuring.
