# Contract: Two Wallet-History Stories

**Feature**: `007-featured-enrichment`  
**Owns**: FR-012, FR-014

## Story A — Lifetime hydrate (featured)

On first featured sight of a `proxy_wallet` without a current wallets version:

- Budgeted Data API walk (`/v2/user-stats`, capped trades/activity with `taker_only=false` and `end` at `trade_ts`, closed positions as applicable).
- Persist pre-`trade_ts` facts; cache a `wallets` version.
- Cap pages/time → `wallet_hydrate_status=partial`; budget skip → `skipped_budget` / `pending`; failure → `failed`.
- `lifetime_is_first_trade` is `true` only on a **complete empty** walk; else `null`.

## Story B — Archive-path wallet features

Derived from the local admitted `trades` tape (and later fills) for that `proxy_wallet`. Not interchangeable with hydrate.

## Stratification (required)

Any analysis combining hydrate and archive-path wallet features MUST stratify by `wallet_hydrate_status` (and funding exactness flags when used). Silent lifetime↔archive hybrids are rejected.

## Funding dimension

`proxy_funding` writers: scheduled Dune sync + Transfer-log miss/top-up. Snapshot fields rematerialize with `known_at` ≤ `trade_ts`; event-sourced edges by event time before `trade_ts`. No per-fill Dune calls.
