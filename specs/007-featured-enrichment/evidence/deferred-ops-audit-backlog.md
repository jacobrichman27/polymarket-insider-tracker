# Deferred ops / honesty audit backlog (featured enrichment)

**Logged**: 2026-11-26  
**Slice**: `007-featured-enrichment`  
**Status**: Deferred to a **future step** after PR/merge of the local implement. Do **not** treat unit tests or static/services green as substitute for these audits.

**Prerequisite**: Real receipt decode with a closed `onchain_direction` vocabulary and disposable (non-burn-in) tape/enrichment cohort. Until then, any partial audit must label `receipt_incomplete`.

**Method sketch** (when run): stratified cohort export → automated rates → sampled forensic review → append-only evidence under this directory → only then publish KPI / consider gap close. Details discussed in session; execute on scratch Postgres only.

## Backlog (must audit later)

| ID | Topic | What to verify | Related |
| --- | --- | --- | --- |
| A-001 | Receipt decode ground truth | Closed vocabulary for `onchain_direction` (`buy`/`sell`/`mint`/`merge`/…); `log_index` / `block_number`; maker–taker when exposed; `receipt_status` honesty vs stub/`pending` | G-047; FR-004; Data.md receipts |
| A-002 | Weak fingerprint canonicalization | Fixed-scale price/size aliases collide; tx lowercasing; fail-closed without price/size; no `side`/`proxy_wallet` in key (`b.v2+`) | G-049; `fingerprint.py`; contract §fingerprint-and-order |
| A-003 | Weak fingerprint collisions | Rate of keys with `assess_weak_collision` (observation_count > 2 or same_side_max > 1); sample multi-maker same price/size txs; under-merge from fee/rounding | G-049; Data.md “Measure once collecting” |
| A-004 | Strong vs weak rematerialize | When locators arrive, strong FP / `fully_enriched` rematerialize; frozen `live_as_of` not overwritten; no silent strong+weak mix in one primary slice | G-049; FR-009–FR-010 |
| A-005 | Multi-maker sweep grain | One taker × N makers → N slice fingerprints (distinct price/size); API legs pair per slice; `fills_in_tx` / same-tx counterparties | Data.md `fills_in_tx`; fingerprint contract |
| A-006 | Signed-flow disagreement KPI | Histogram `agree` / `complement` / `mint_merge` / `true_mismatch` / `unavailable` on ~1k `receipt_status∈{ok,partial}`; publish before λ/imbalance Core overweight | G-050; FR-011; `DisagreementClass` |
| A-007 | Mint/merge labeling | Decoder marks CTF split/combine; string/`mint`/`merge` heuristic matches chain reality; sampled Polygonscan review | G-050; Data.md signed-flow gate |
| A-008 | True mismatch residual | Sample `true_mismatch` for decoder bugs vs real anomalies; version ceilings before gate pass | G-050 |
| A-009 | Convention ≠ aggressor | Market λ/imbalance still use API `side` on fingerprint-deduped canonical leg; never arrival-order-as-aggressor; convention-leg vs receipt aggressor when available | G-050; contract §signed-flow-kpi |
| A-010 | Featuring / arm statuses | Per-arm statuses explain nulls; degrade-from-bottom; markets never skipped; budget skip honesty on live cohort | G-047; FR-004–FR-006 |
| A-011 | FR-017 hybrid reuse | Receipt once per tx/fingerprint; funding/hydrate once per proxy; tape pair-assist for unfeatured opposite legs | FR-017 |
| A-012 | Regime-upgrade hot backfill | Insert-time `unknown` → later `private_edge_possible` enqueues only while still hot; no trades knowability rewrite; left-hot / no_private_edge exclusions | G-048; FR-007–FR-008 |
| A-013 | Wallet-history dualism | `wallet_hydrate_status` stratification; no silent lifetime↔archive hybrid; `lifetime_is_first_trade` null-unless-complete-empty; full Data-API hydrate walk | G-051; FR-012 |
| A-014 | Funding miss/top-up | Transfer-log path (no per-fill Dune); rematerialize `known_at` ≤ `trade_ts`; Dune bulk lag vs Transfer hit rate | FR-014; Data.md measure-once |
| A-015 | Wash-adjusted demotion | Wash-cleaned volume stays Useful/Partial under featuring gate until separate approval (T050) | FR-016 |
| A-016 | Health isolation | Enrichment lag / signed-flow KPI degraded ≠ `trade_archive` down / ready fail; assessment persist still non-blocking | Decision 11; SC-008 |
| A-017 | Analysis readiness gates | Fingerprint-dependent Core aggregates blocked until locked strong rematerialize; λ Core blocked until KPI published | SC-004; SC-005 |

## Explicit non-goals for this backlog

- Closing G-047–G-051 from unit tests alone  
- Running against the configured burn-in / application database  
- Inventing cleverer weak keys mid-audit without `ARCHIVE_FINGERPRINT_VERSION` bump  
- Treating `complement` as error or `agree` as aggressor truth  

## Follow-on execution

Append Spec Kit tasks (or a small follow-on slice) when ready: receipt vocabulary → audit script/export → evidence receipt → KPI publish. Track progress by checking off rows here with dated evidence links; do not rewrite this list to imply earlier completion.

## Live monitoring vs this backlog

In-process metrics / `featured_enrichment` diagnostic (2026-11-26) catch **operational** red flags (loop/enqueue errors, arm status rates, signed-flow counter plumbing). They do **not** close A-001–A-017. Operator catalog: [`docs/collection-honesty-monitoring.md`](../../../../docs/collection-honesty-monitoring.md). Gap **G-054** tracks remaining Alertmanager / cohort publish work.

## Related field-delivery slices (not this backlog)

Ops audit here proves **arm honesty** for the 007 platform (G-047–G-051). It does **not** own Data.md §§1–6 catalog completeness:

| Phase | Slice (proposed) | Gap | Owns |
| --- | --- | --- | --- |
| B.1 | `010-featured-core-features` | G-052 | Core producers + Core `trade_features` materialization |
| B.2 | `011-featured-useful-features` | G-053 | Remaining Useful rows so the intended catalog eventually lands |

Specify/implement B.1 after 007 merge + enough of this audit that statuses are trustworthy (especially A-001 receipt vocabulary and A-013/A-014 hydrate/funding honesty).
