# Contract: Featuring Gate

**Feature**: `007-featured-enrichment`  
**Owns**: FR-001, FR-002, FR-007, FR-008, classifier-control (clarify)

## Eligibility

A fill is **featured-eligible** when all hold:

1. Archive writing enabled and `ARCHIVE_FEATURING_ENABLED=true` (requires archive on).
2. Knowability regime from A1 markets snapshot (`known_at` ≤ `trade_ts`) is
   `private_edge_possible` (legacy `private_settlement_possible` /
   `private_factor_possible` remain eligible during transition).
3. Per-fill `notional_usdc` ≥ versioned cutoff (provisional default **5000**).

Otherwise not featured, with an explicit reason code.

## Defaults and rejects

- `unknown` and `no_private_edge`: **not** featured by default.
- `unknown` opt-in: only via versioned featuring/knowability-policy bump with rationale.
- Must **not** block trades insert or observation emission.

## Classifier-control sample

A small seeded random sample of otherwise featuring-rejected `no_private_edge` fills MAY enter a limited enrichment path for classifier audit. Sample rate is versioned (plan provisional **0.1%**, bounded). Must not become full enrichment of that population.

## Regime-upgrade backfill

When markets regime becomes featuring-eligible (`private_edge_possible`):

- Enqueue featuring for already-stored fills that (1) remain in **hot** window, (2) meet notional cutoff, (3) have not completed/abandoned enrichment for current `enrichment_budget_version`.
- **Hot** means still inside the configured hot retention window **at enqueue decision time** (A0 hot/retention setting; provisional ~14 days within Data.md’s 7–30 day band). Exact setting name pinned in implement/tests.
- Boundary race: a fill whose `trade_ts` is at/just past the hot horizon when upgrade enqueue runs MUST NOT be treated as newly receipt-enrichable; concurrent “leaving hot while enqueue runs” MUST exclude or no-op without claiming enrichment for that row.
- Upgrade to `no_private_edge`: **no** featured enqueue.
- Left hot without enrichment: permanent miss for those arms unless later amendment.

A1 writes regime; B owns enqueue/worker. Do not rewrite historical trades knowability columns.
