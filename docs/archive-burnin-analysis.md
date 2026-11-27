# Archive burn-in analysis (agent procedure)

How post-run analysis is done for early tape/featuring burns. **Not** a human checklist.

**Phase note:** This framework is for **current** archive + featuring-platform burn-in
(A0/A1/007). It **will change** as later phases land (Core fields in 010, Useful in 011,
labels in C, retention in D). When a phase ships new fields or honesty rules, update this
doc and `scripts/archive_burnin_report.py` in the same change — do not keep analyzing
against an obsolete field set.

Production featuring cutoff stays **$5000**. Early analysis burns use **`$500`** via
`ARCHIVE_FEATURING_NOTIONAL_CUTOFF_USDC=500` (env override only).

## Run contract

Before start, record: git SHA, wall duration, health port, and flags
(`ARCHIVE_ENABLED`, `ARCHIVE_FEATURING_ENABLED`, `ARCHIVE_COLLECT_PRIORITY`,
featuring cutoff, repair). Write `RUN_MARK` (UTC) at process start; `ENDED_AT` at stop.
Restarts and `ingest_gap_events` are outcomes to report, not noise to hide.

Suggested collect command shape:

```bash
ARCHIVE_ENABLED=true \
ARCHIVE_COLLECT_PRIORITY=true \
ARCHIVE_FEATURING_ENABLED=true \
ARCHIVE_FEATURING_NOTIONAL_CUTOFF_USDC=500 \
ARCHIVE_OUTCOME_REPAIR_ENABLED=true \
uv run --env-file .env python -m polymarket_insider_tracker --dry-run --health-port 8088
```

## After the run

1. Stop the pipeline; confirm no leftover process on the health port.
2. Run the fixed pack:

```bash
uv run --env-file .env python scripts/archive_burnin_report.py \
  --mark-file /tmp/live_run_30m_mark.txt \
  --out /tmp/burnin_report.json
```

3. Present to the user: **issue_flags first**, then section highlights, then a canvas for
   the sample gallery. Every **key field** must show a **full value breakdown** (not only
   “% missing”). If a distribution looks off, call it out explicitly.

### Presentation sections

| Section | Purpose |
| --- | --- |
| Run meta | Marks, wall span, restarts, early vs production cutoffs |
| Acquisition | inserts/min, lag p50/p95, gaps |
| Key field breakdowns (window) | Full counts for every key categorical + presence field on `trades` |
| Key field breakdowns (completed enrich) | Same fields on completed work-item trades only |
| Featuring / queue | reason mix; first-vs-later unknown; work trigger×status |
| Markets | policy version + regime + label_source + source_version breakdowns |
| Early lens ($500) | Full key-field breakdowns for `notional ≥ 500` |
| Production lens ($5k) | Full key-field breakdowns for `notional ≥ 5000` |
| Unexpected values | Any key-field values outside the allowlist |
| Sample gallery | Five representative full-table bundles (canvas) |

## Key fields (current phase)

Categorical — always emit `{value: count}` including `null`:

- `side`, `source`
- `outcome_repair_status`, `receipt_status`, `gamma_enrichment_status`
- `funding_lookup_status`, `wallet_hydrate_status`
- `featuring_reason`, `info_knowability_regime` (`no_private_edge` /
  `private_edge_possible` / `unknown`;
  legacy `private_edge_possible` still counted), `knowability_label_source`
- `fingerprint_version`, `featuring_config_version`, `enrichment_budget_version`

Allowlists in `scripts/archive_burnin_report.py` match current producer vocab; values
outside those sets become `unexpected_values:*` issue flags.

Presence / nullability — always emit `{present, null}` (and true/false/null for `neg_risk`):

- `raw_row_json`, `fill_fingerprint`, `outcome`, `neg_risk`
- `block_number`, `log_index`, `onchain_direction`, `fee_usdc`, `counterparty_wallets`

Markets (rows with `known_at` in window): `knowability_policy_version`,
`info_knowability_regime`, `knowability_label_source`, `source_version`.

Work items (`enrichment_work_items`): `trigger` × `status` crosstab.

## Issue signals

Auto `issue_flags` plus narrative review of breakdowns:

- Acquisition holes / restart-beyond-horizon
- Unexpected categorical values (legacy regimes, unknown statuses, etc.)
- Completed enrichment **lying** (gamma/hydrate `ok` while stubs; features with receipt pending)
- Live path starved (`insert_time` behind `regime_upgrade`)
- Thin early/$5k cohorts
- Mass `failed` / odd arm mixes on completed work
- Window trades all `unknown` while markets in-window are classified

Stubs that stay `pending` (receipt/funding/hydrate) are **known gaps** until 010/real arms —
flag only if vocabulary claims `ok` or statuses fall outside the allowlist.

Window bounds use `trades.observed_at` and `notional_usdc` (not `price * size`).
