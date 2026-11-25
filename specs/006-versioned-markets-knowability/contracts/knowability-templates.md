# Contract: Knowability Template Allowlist & Normalizer

**Feature**: `specs/006-versioned-markets-knowability`  
**Date**: 2026-11-24 (amended 2026-11-25 — version stamp rename + matching short-circuit)  
**Parent**: [knowability.md](knowability.md) · normative examples in [`Data.md`](../../../Data.md) Knowability

## Purpose

When Gamma `seriesSlug` is missing or too coarse, try a **deterministic** map from market question text → one **allowlisted** `template_id`, then reuse the template cache. This runs **before** any Decisions API call. The model never invents template ids.

## Ship decision: matching disabled

`template_allowlist_version` = `knowability.templates.v1` **reserves** the three ids below but **does not run cue matching**. Product code sets `TEMPLATE_MATCHING_ENABLED=false` so the template lookup step is **skipped** (no match, no template-cache seed from automatic match). Classification falls through to series (already tried) then Decisions when effectively enabled. Rationale: substring cue sets have high false-positive risk and cover only a tiny market share; prefer miss over a wrong regime stamp on `markets`.

Re-enabling matches requires a new allowlist version (`knowability.templates.v2`+) with high-precision rules, flipping `TEMPLATE_MATCHING_ENABLED`, contract update, and fixtures — not silent cue growth under `knowability.templates.v1`.

(Historical planning name `a1.v1` refers to this same reserved allowlist.)

## Reserved ids (`knowability.templates.v1`)

| `template_id` | Default regime (if ever seeded) | Onset policy | Intent |
| --- | --- | --- | --- |
| `CRYPTO_UP_OR_DOWN_WINDOW` | `never_early` | null | Short-horizon crypto / spot price path |
| `SPORTS_MATCHUP_WINNER` | `always_latent` | null | Head-to-head sports winner / matchup |
| `EARNINGS_BEAT_EPS` | `always_latent` | null | Company earnings beat/miss / EPS |

No other template ids are valid until a versioned bump. Human **template** overrides in Postgres still win at lookup step 1 when keyed by these ids **and** matching is enabled (or when overrides are applied by `template_id` directly in a later path).

## Behavior when matching is disabled

1. Normalize/match are unused for production classification; the template step is short-circuited.
2. Template cache is not written from automatic match (overrides/series/model paths unchanged).
3. Miss → proceed to Decisions (if enabled) for **this market’s regime only**.

## Explicit non-goals

- No model-proposed template ids.
- No open-ended clustering of questions into new templates.
- No active dumb-normalizer cue matching in shipped `knowability.templates.v1`.
- No awards / locked-tally `windowed` template until a later allowlist version.

## Testability

Fixtures MUST prove `TEMPLATE_MATCHING_ENABLED` is false and `match_template` returns `None` for representative crypto / sports / earnings / unrelated questions (and with category tags). Reserved id constants remain present for a future bump.
