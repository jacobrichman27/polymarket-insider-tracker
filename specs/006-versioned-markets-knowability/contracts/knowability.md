# Contract: Knowability Classification

**Feature**: `specs/006-versioned-markets-knowability`  
**Date**: 2026-11-23 (amended 2026-11-24 — model default / budget; 2026-11-25 — version stamps / provisional windowed / template short-circuit)  
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

**Default model adapter:** OpenAI Decisions API (`POST /v1/decisions`, `gpt-6-luna`) with bounded `choice` (and related) questions for regime classification. Version the adapter; credentials via existing secret-safe config patterns.

**Policy stamp:** `knowability.v2` (series/override policy version in product code; `v1` = initial Decisions copy; `v2` = principle-based privileged-edge definitions without category examples).

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

`never_early` | `always_latent` | `windowed` | `unknown`

- `windowed` **with** onset / `knowable_from` is complete per Data.md. `windowed` **without** onset is allowed as **provisional** (distinct from `unknown`) until onset enrichment; do not collapse it into `unknown`. Do not force earnings-style calendars into `windowed`.
- All regimes remain admitted on the trades tape; never drop `never_early` or `unknown`.

## Upgrade semantics

New markets version on classification/upgrade. **Do not** rewrite historical trades knowability columns. Trade-time research joins markets. Featuring backfill of stored hot fills is Phase B.

## Policy versioning

`knowability_policy` version stamps (`knowability.v2` current) apply forward. Do not mix versions silently in one analysis slice.
