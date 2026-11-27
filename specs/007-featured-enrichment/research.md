# Research: Featured Enrichment (Phase B)

**Feature**: `specs/007-featured-enrichment`  
**Date**: 2026-11-25  
**Status**: Phase 0 complete — clarify locks + Data.md decisions; no open NEEDS CLARIFICATION in Technical Context.

## Decision 1 — Featuring gate

**Decision:** Feature when regime is `private_edge_possible` **and** notional ≥ versioned cutoff (provisional **$5000**). `unknown` and `no_private_edge` are not featured by default. `unknown` opt-in requires explicit versioned policy/config bump.

**Rationale:** Spec clarifications 2026-11-25 + Data.md Featuring lock. Cost gate, not recall guarantee.

**Alternatives considered:** Feature all admitted fills (rejected — cost); feature `unknown` by default (rejected); lower cutoff without versioning (rejected).

## Decision 2 — Async workers; never block insert

**Decision:** Featuring evaluation and enrichment run off the Archive insert / poller hot path (background tasks / durable work items). Injected RPC/Gamma/hydrate latency MUST NOT stall policy-(a) insert or emission.

**Rationale:** Same hard rule as A1; A0 burn-in showed monitor/enrichment on the hot path causes horizon loss.

**Alternatives considered:** Inline enrichment after insert in the delivery callback (rejected); shared event-loop blocking awaits (rejected).

## Decision 3 — Enrichment arm order and degrade

**Decision:** Attempt order: markets/Gamma → receipt → Transfer-log funding (miss/top-up) → lifetime hydrate (miss). Degrade bottom-up under budget. Do not skip markets/Gamma for featured rows—record failure and continue. Every arm gets an explicit status.

**Rationale:** Data.md Enrichment decisions. Provisional caps: ~60s wall, ~8 Polygon RPCs, ~10 hydrate pages or ~15s — **revise after ops measurement**.

**Alternatives considered:** Receipt before Gamma (rejected — markets context first); silent nulls (rejected).

## Decision 4 — FR-017 both-leg hybrid

**Decision:** Per-observation featuring eligibility; reuse shared arms by natural grain (receipt once per tx/fingerprint; funding/hydrate once per proxy/wallet); tape fingerprint pair-assist for counterparties on unfeatured opposite/small legs.

**Rationale:** Operator + planner recommendation 2026-11-25 — long-term cost and honesty without orphaning small-leg edges.

**Alternatives considered:** Full independent double-spend of all arms (rejected); require small leg to clear gate before any counterparty edge (rejected).

## Decision 5 — Regime-upgrade hot backfill

**Decision:** On markets regime upgrade to featuring-eligible `private_edge_possible`, enqueue featuring for hot, notional-eligible fills not already completed/abandoned for current `enrichment_budget_version`. Upgrades to `no_private_edge` do not enqueue. Left-hot rows are permanent enrichment misses for those arms without a later amendment.

**Rationale:** Data.md locked backfill; A1 owns regime write, B owns enqueue/worker.

**Alternatives considered:** Insert-time featuring only (rejected); global historical backfill (rejected — collection rule 5 / cost).

## Decision 6 — Fingerprint and order-as-of

**Decision:** Version `fingerprint_version` for strong (tx, token, log_index when present) vs weak (tx, token, price, size). Materialize order-dependent fields with `order_as_of_contract` ∈ {`live_as_of`, `fully_enriched`}. Never overwrite frozen `live_as_of` in place when peers later gain locators—new `feature_version` / rematerialize instead. Primary studies gated until rematerialized under locked fingerprint version (weak sensitivity strata allowed if labeled).

**Rationale:** Data.md Canonical tables + Order as-of contract.

**Alternatives considered:** Treat weak as Core forever (rejected); rematerialize live equals always (rejected).

## Decision 7 — Signed-flow KPI gate

**Decision:** Market-tape signed aggregates use API `side` on fingerprint-deduped convention canonical leg. Publish disagreement KPI vs receipt `onchain_direction` / aggressor evidence before λ/imbalance are first-class Core inputs.

**Rationale:** Data.md Signed-flow / aggressor gate; API has no aggressor role.

**Alternatives considered:** Treat convention as aggressor truth (rejected).

## Decision 8 — Two wallet-history stories

**Decision:** Lifetime hydrate (featured, budgeted Data API walk) and archive-path wallet features remain distinct; always persist/stratify `wallet_hydrate_status`. `lifetime_is_first_trade` true only on complete empty walk.

**Rationale:** Data.md Two wallet-history stories.

**Alternatives considered:** Merge hydrate into archive features silently (rejected).

## Decision 9 — Classifier-control sample

**Decision:** Keep a small seeded random sample of featuring-rejected `no_private_edge` fills for classifier control. Exact rate chosen in tasks/implement (provisional plan default **0.1%** of rejected eligible markets/fills, min 1 / max configurable). Must not widen into full enrichment of that population.

**Rationale:** Operator clarify 2026-11-25 + Data.md Knowability control note.

**Alternatives considered:** No sample (weaker classifier audit); enrich all `no_private_edge` (rejected).

## Decision 10 — Config surface

**Decision:** Featuring behind explicit archive-related settings (default: featuring/enrichment **off** until enabled, or enabled only when archive on + `ARCHIVE_FEATURING_ENABLED`—plan locks **separate** `ARCHIVE_FEATURING_ENABLED` default **false**, requires `ARCHIVE_ENABLED`). Budget/cutoff/version fields are versioned settings. No execution knobs.

**Rationale:** Matches A1 pattern (archive on, feature work on separate flag); safer for laptop burn-in hosts.

**Alternatives considered:** Auto-on with archive (riskier under load); third process (deferred).

## Decision 11 — Health isolation

**Decision:** Enrichment lag/KPI may surface diagnostic components or metrics; MUST NOT mark `trade_archive` **down** solely because enrichment is behind. Tape readiness remains insert/owed/backlog SLOs from 003/005.

**Rationale:** Dual-use health honesty; A1 repair KPI pattern.

**Alternatives considered:** Fail `/ready` on enrichment backlog (rejected — conflates tape with enrich).
