# B Featured Enrichment Requirements Checklist: Featured Enrichment (Phase B)

**Purpose**: Before coding, check that the written B requirements are clear and complete enough to build from. This is a review of the *docs*, not a test that the code works yet.  
**Created**: 2026-11-25  
**Feature**: [spec.md](../spec.md) · [plan.md](../plan.md) · [research.md](../research.md)

**Note**: This is a reviewer-owned requirements-quality checklist.  
**Review Ownership**: You (the repository owner of this fork), or someone you designate, decide each `[x]` (constitution 2.1.0).  
**Marker Semantics**: `[x]` means “this requirement is written clearly enough.” It does **not** mean the feature is implemented.  
**Implementation Gate**: Agents must not tick these boxes for you.

**Focus**: Full Phase B (featuring gate, budgeted enrichment, hot backfill, fingerprint/order-as-of, signed-flow KPI, wallet dualism, research-only). **Depth**: Standard (peer to A0/A1 domain checklists).

## Scope & Out of Bounds

- [x] CHK001 Does B clearly say what it will **not** build (Phase C labels/resolutions, Phase D compaction, trading execution, silent `unknown` featuring, wash-adjusted Core promotion)? [Completeness, Spec §US7; Plan §Summary]
- [x] CHK002 Is B explicitly dependent on A0 tape + A1 markets/knowability without redefining insert identity or `trade_archive` SLOs? [Consistency, Spec §Assumptions; Plan §Constraints]
- [x] CHK003 Is featuring/enrichment required to be **non-blocking** relative to observation emission and trades insert? [Clarity, Spec §FR-003; Research Decision 2]



## Featuring Gate & Defaults

- [x] CHK004 Is featuring behind a **separate** explicit setting that **defaults to off** and requires archive writing on? [Clarity, Research Decision 10; Contract §b-config-and-health]
- [x] CHK005 Are gate inputs locked as regime `private_edge_possible` **and** notional ≥ versioned cutoff with provisional **$5,000**? [Measurability, Spec §Clarifications, §FR-001]
- [x] CHK006 Is `unknown` featuring **off by default**, with opt-in only via explicit versioned policy/config bump? [Consistency, Spec §Clarifications Q4, §FR-002]
- [x] CHK007 Is the classifier-control sample for `no_private_edge` required as a **small seeded** path that must not widen into full enrichment of that population? [Clarity, Spec §Clarifications Q3; Research Decision 9]



## Enrichment Budget, Arms & Both-Leg Policy

- [x] CHK008 Are arm order and degrade-from-bottom rules written (markets → receipt → funding → hydrate; never skip markets/Gamma for featured rows)? [Completeness, Spec §FR-004–FR-005; Contract §enrichment-budget]
- [x] CHK009 Are provisional caps stated as **revisable after ops data** (not frozen SLOs), with `enrichment_budget_version` required on change? [Clarity, Spec §Clarifications Q2; Research Decision 3]
- [x] CHK010 Is per-arm status honesty required (no silent nulls)? [Completeness, Spec §FR-006]
- [x] CHK011 Is the FR-017 **hybrid** both-leg policy locked (per-observation eligibility; reuse receipt/funding/hydrate by natural grain; tape pair-assist for unfeatured opposite legs)? [Consistency, Spec §Clarifications Q1, §FR-017]



## Regime-Upgrade Hot Backfill

- [x] CHK012 Is hot-window enqueue on upgrade to `private_edge_possible` required, with exclusions for completed/abandoned work and for upgrades to `no_private_edge`? [Completeness, Spec §FR-007–FR-008; Contract §featuring-gate]
- [x] CHK013 Is “left hot without enrichment = permanent miss for those arms without later amendment” stated? [Edge Case, Spec §US3 §3]
- [x] CHK014 Is ownership split clear (A1 writes regime; B owns enqueue/worker; no trades knowability rewrite)? [Consistency, Spec §US3 §4]



## Fingerprint, Order-As-Of & Signed Flow

- [x] CHK015 Are strong vs weak fingerprint rules and `fingerprint_version` primary-analysis gating specified? [Completeness, Spec §FR-009; Contract §fingerprint-and-order]
- [x] CHK016 Are `live_as_of` vs `fully_enriched` contracts and no in-place overwrite of frozen `live_as_of` required? [Clarity, Spec §FR-010]
- [x] CHK017 Is convention-signed market λ using API `side` on fingerprint-deduped canonical leg, with a receipt disagreement KPI gate before Core overweighting? [Completeness, Spec §FR-011; Contract §signed-flow-kpi]



## Wallet History Dualism

- [x] CHK018 Are lifetime hydrate and archive-path wallet features required to stay distinct and stratified by `wallet_hydrate_status`? [Completeness, Spec §FR-012; Contract §wallet-history]
- [x] CHK019 Is `lifetime_is_first_trade` true only on a complete empty hydrate walk? [Edge Case, Spec §US6 §2]
- [x] CHK020 Are `wallets` / `proxy_funding` rematerialize rules (snapshot vs event-time) stated without per-fill Dune calls? [Consistency, Spec §FR-014; Data.md]



## Safety, Health & Acceptance

- [x] CHK021 Are dry-run delivery isolation and no execution surface required when featuring is enabled? [Completeness, Spec §FR-015; Contract §b-config-and-health]
- [x] CHK022 Is enrichment lag forbidden from alone marking `trade_archive` **down** / failing tape readiness? [Consistency, Research Decision 11]
- [x] CHK023 Do success criteria SC-001–SC-008 map to testable outcomes without implementation stack leakage? [Measurability, Spec §Success Criteria]
- [x] CHK024 Are wash-adjusted market stats kept Useful/Partial (not Core) under the featuring gate until a separate approval? [Consistency, Spec §FR-016]



## Notes

- Leave items unchecked until the repository owner (or designate) reviews.
- After checklist review, record human validation on `tasks.md` T001 before `$speckit-implement`.

