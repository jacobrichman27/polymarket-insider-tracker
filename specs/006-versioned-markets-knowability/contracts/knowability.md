# Contract: Knowability Classification

**Feature**: `specs/006-versioned-markets-knowability`  
**Date**: 2026-11-23 (amended 2026-11-24 — model default / budget; 2026-11-25 — version stamps / template short-circuit / binary regimes v3)  
**Normative regimes / lookup**: [`Data.md`](../../../Data.md) Knowability

## Lookup order (first hit wins)

1. Human override (series or template id) — durable Postgres override table (append-on-change); optional seed file may bootstrap
2. Gamma `seriesSlug` cache
3. **Exact question-text cache** — NFKC + casefold + collapsed whitespace; key = SHA-256 of normalized text scoped by `knowability` policy version. Hits reuse a prior Decisions (or seeded) regime across different `condition_id`s with the same title. `label_source=question`.
4. **Allowlisted deterministic template match** — **before** any model call when matching is enabled. Normative allowlist: [knowability-templates.md](knowability-templates.md) (`knowability.templates.v1` reserves `CRYPTO_UP_OR_DOWN_WINDOW`, `SPORTS_MATCHUP_WINNER`, `EARNINGS_BEAT_EPS` but **ships with matching disabled** / short-circuited; miss → Decisions when enabled).
5. Optional cheap model on miss/low confidence **only when effectively enabled** (see below)

**Template (plain meaning):** a normalized question pattern with specifics slotted out so many listings share one cached regime when Gamma series is missing or too coarse. Ids come only from the versioned allowlist; the model MUST NOT invent ids. Empty allowlist / disabled matching is OK.

**Question cache (plain meaning):** reuse the regime for an identical market title when series/template miss. Does **not** generalize across different titles (e.g. Austin 28–29°F vs 34–35°F stay distinct).

Record `knowability_label_source` on the markets version (and optional stamp on new trades inserts). Successful non-`unknown` model classifications MUST write through to the **series** cache when a series id is present **and** to the **question** cache when the question normalizes non-empty (not into free-form templates).

**Default model adapter:** OpenAI Decisions API (`POST /v1/decisions`, `gpt-6-luna`) with a single bounded `choice` question for regime classification. Version the adapter; credentials via existing secret-safe config patterns. No onset / `knowable_from` question under `knowability.v5`.

**Policy stamp:** `knowability.v5` (product code; `v1` = initial Decisions copy; `v2` = principle-based privileged-edge definitions; `v3` = binary `no_private_edge` / `private_edge_possible` / `unknown`; `v4` = brief settlement/factor split; `v5` = collapse back to binary privileged edge, no live onset). Current model adapter prompt: `knowability.prompt.v8` (public-process vs privileged-channel settlement test; moneyline/spread/handicap and held finished results → private; season/public accumulation → no_edge; Decisions evidence includes clipped resolution source + description). Easy public title shapes (temperature, up/down, tweets/Truth Social, O/U totals, exact score, in-event) short-circuit before Decisions as `label_source=title_rule`.

**Golden set (opt-in):** Frozen human-agreed titles live under `evals/knowability/` and run via `scripts/knowability_golden.py` (offline stub by default; `--live` for Decisions). Same isolation rule as the trades smoke check: never part of `verify.py` profiles or CI. See `evals/knowability/README.md`.

## Model-on-miss enablement & spend guardrails

| Setting | Env | Default | Rules |
| --- | --- | --- | --- |
| Model intent | `ARCHIVE_KNOWABILITY_MODEL_ENABLED` | `true` | Force **off** with `false`. Effective on also requires configured model credentials |
| Daily call budget | `ARCHIVE_KNOWABILITY_MODEL_MAX_CALLS_PER_DAY` | `10000` | Hard stop for UTC day; over budget → no further model calls |

**Effective enablement:** credentials present **and** `ARCHIVE_KNOWABILITY_MODEL_ENABLED` is not `false`.  
**No credentials** → effective off (leave `unknown` on miss); MUST NOT crash or stall insert.  
**Grain:** model calls only for market/series/template classification misses — **never per fill**.  
**Circuit-breaker:** elevated error/timeout rate opens the circuit → same as over-budget (`unknown` + alarm).  
**Acceptance:** remaining possible without a live vendor (no credentials / forced off in tests).

## Regimes

`no_private_edge` | `private_edge_possible` | `unknown`

- Timing of when privileged knowledge might appear does **not** create another class.
- Privileged edge is a single regime; do not split settlement-fact vs intermediate-factor at classification time.
- `markets.knowable_from` remains nullable for legacy rows and is unused under `v5` (classifications write `NULL`).
- All regimes remain admitted on the trades tape; never drop `no_private_edge` or `unknown`.
- Featuring (Phase B) gates on `private_edge_possible` (plus notional cutoff). Legacy `private_settlement_possible` / `private_factor_possible` remain featuring-eligible during transition.

## Upgrade semantics

New markets version on classification/upgrade. **Do not** rewrite historical trades knowability columns. Trade-time research joins markets. Featuring backfill of stored hot fills is Phase B.

## Policy versioning

`knowability_policy` version stamps (`knowability.v5` current) apply forward. Do not mix versions silently in one analysis slice. Historical `v1`/`v2`/`v3`/`v4` rows with legacy regime names remain as stored history.
