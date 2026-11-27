# Contract: Signed-Flow / Aggressor KPI

**Feature**: `007-featured-enrichment`  
**Owns**: FR-011

## Market-tape signed aggregates

For λ, imbalance, Yes-equivalent signed notional:

1. Dedupe to match grain via fingerprint.
2. Choose convention canonical leg by Collection rule 6 when receipt does not identify taker.
3. Sign using API `side` on that leg — **not** arrival order as aggressor truth.

Unsigned volume and side-filtered burst/size counts do not use that signer.

## Receipt disagreement KPI

On featured cohorts with `receipt_status` in {`ok`, `partial`}, classify agreement between convention/API side and `onchain_direction` / maker-taker when exposed. Persist rates / histogram as a first-class KPI for the enrichment/`feature_version` cohort.

Example classes: agree; complement; mint–merge; true mismatch; unavailable.

## Gate

Primary studies and any future scoring MAY treat λ / signed imbalance / initiator features as first-class Core inputs **only after** the KPI is published for the deployed cohort and disagreement classes are labeled. Until then: Useful/sensitivity only or explicit “convention-signed” stratum.
