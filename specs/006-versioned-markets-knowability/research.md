# Research: Versioned Markets & Knowability (Phase A1)

**Feature**: `specs/006-versioned-markets-knowability`  
**Date**: 2026-11-23  
**Status**: Phase 0 complete — clarify locks + A0/Data.md decisions; no open NEEDS CLARIFICATION in Technical Context.

## Decision 1 — Forward-only repair with explicit cutover

**Decision:** Repair only rows inserted after `ARCHIVE_OUTCOME_REPAIR_ENABLED` becomes true. Persist durable `repair_enabled_at` (UTC) on collector/A1 state at first successful enable; KPI population is `observed_at`/`trade_ts` ≥ cutover (plan uses insert-time ≥ `repair_enabled_at`).

**Rationale:** Operator clarify 2026-11-22 — early/burn-in tape is not for analysis. Avoids forcing catch-up of non-analysis rows into the unrepaired KPI.

**Alternatives considered:** Catch-up all hot rows (rejected); opt-in backfill flag as default (rejected for default A1).

## Decision 2 — Separate repair setting vs archive

**Decision:** `ARCHIVE_OUTCOME_REPAIR_ENABLED` default `false`; requires `ARCHIVE_ENABLED=true`. Archive-on alone does not start repair.

**Rationale:** Clarify lock — operators can collect raw tape, warm markets, then flip repair when ready for analysis-eligible inserts.

**Alternatives considered:** Tie repair to archive (rejected); always-on at deploy (rejected).

## Decision 3 — Markets writers vs repair gate

**Decision:** Versioned `markets` + knowability cache writers run when `ARCHIVE_ENABLED`; independent of repair flag.

**Rationale:** Clarify lock — warm metadata before repair cutover without polluting repair KPI.

**Alternatives considered:** Same gate as repair; third independent markets flag (extra ops surface, deferred).

## Decision 4 — Regime authority = markets snapshot join

**Decision:** Trade-time regime from latest `markets` version with `known_at` ≤ `trade_ts`. Do not rewrite historical trades knowability columns on upgrade. New inserts MAY stamp current regime when known.

**Rationale:** Clarify + Data.md snapshot-only dimensions; avoids false history. Phase B owns featuring backfill queue.

**Alternatives considered:** Mutate trades on upgrade; hot-window dual-write (deferred complexity).

## Decision 5 — Async workers; never block insert

**Decision:** Enqueue or schedule repair/classification off the Archive insert / poller hot path (background task or post-commit queue). Injected Gamma latency MUST NOT stall policy (a) insert or emission.

**Rationale:** Hard A* latency rule; FR-002.

**Alternatives considered:** Inline Gamma on insert (rejected); shared thread with poller without isolation (rejected).

## Decision 6 — Repair KPI provisional numbers

**Decision:** Attempt lag default **300s (5 min)** after insert for post-cutover thin rows; unrepaired share ceiling **5%** of thin post-cutover rows over trailing 24h. Tunable via settings; revise with ops without dropping KPI requirement.

**Rationale:** Data.md “minutes” / ≤5% starting point; plan needs concrete defaults for tasks/tests.

**Alternatives considered:** Leave unspecified until implement (rejected — acceptance needs numbers).

## Decision 7 — Model-on-miss on when credentials exist (amended 2026-11-24)

**Decision:** Effective model-on-miss is **on when model credentials are configured**, **off** when absent or when `ARCHIVE_KNOWABILITY_MODEL_ENABLED=false` (force off). Setting default intent is **enabled** (`true`) so research deployments with keys seed series/template caches without many human overrides. Successful model hits **write through** to caches. Guardrails: market/series/template miss grain only (never per fill); `ARCHIVE_KNOWABILITY_MODEL_MAX_CALLS_PER_DAY` default **10000**; circuit-breaker on elevated error/timeout rate; over-budget/circuit-open → `unknown` + alarm, no insert stall. A1 acceptance remains possible without a live vendor (no credentials / forced off in tests).

**Rationale:** Clarify amendment 2026-11-24 — caches otherwise stay empty; calls are cheap but need a hard ceiling.

**Alternatives considered:** Always off until explicit enable (superseded); always-on without credential gate (rejected); uncapped spend (rejected).

## Decision 8 — Minimal markets schema for repair-first

**Decision:** A1 migration ships `markets` with token→outcome map fields sufficient for repair **before** optional rich knowability columns block ship. Knowability regime fields on the same versioned row when classified; caches are separate versioned tables.

**Rationale:** FR-003 — do not hold repair behind Decisions/knowability-model polish.

**Alternatives considered:** Full knowability schema gate before any repair (rejected).

## Decision 9 — Gap ownership

**Decision:** Register A1 gaps G-044–G-046 (repair KPI, versioned markets, non-blocking knowability) in gap-register at plan time; dispositions Open until implement evidence.

**Rationale:** Spec Kit / AGENTS gap ownership before implement.

## Decision 10 — Live 72h operator DB isolation

**Decision:** Implement/tests use disposable Postgres or non-operator DBs. Do not run destructive migrations/tests against an active burn-in `DATABASE_URL` without operator consent.

**Rationale:** Parallel capacity run must not be harmed by A1 plan/implement.

## Decision 11 — OpenAI Decisions API for model-on-miss (2026-11-24)

**Decision:** Default knowability model adapter = OpenAI **Decisions API** (`POST /v1/decisions`, model `gpt-6-luna`). Use `choice` (regime) and optional fields for windowed onset as bounded questions over market text/JSON. Published pricing (GA notes): **$0.10 / 1M input tokens**, **$0.01 / 1M cached input**, **no output-token charge**. At ≤10 000 calls/day and ~1–3k input tokens/call, uncached order-of-magnitude is roughly **$1–3/day** (often less with cache)—well under “exorbitant” if the daily call cap holds. Availability: Decisions API is generally available per OpenAI docs (2026). A1 still accepts with no credentials.

**Alternatives considered:** Generic chat/Responses structured output (higher latency/cost for this job); Jev-only (not a locked vendor here).

## Decision 12 — Human overrides as durable table

**Decision:** Store overrides in Postgres append-on-change (key: series_id or template_id; value: regime, optional onset policy, notes, `known_at`, policy version). Optional checked-in seed file bootstraps. Wins lookup step 1.

**Rationale:** Auditable, survives redeploy, matches versioned research dims; file-only overrides are clumsy for live ops.

## Decision 13 — Usable API vs Gamma disagreement

**Decision:** Usable API outcome ⇒ `not_needed`; do not Gamma-overwrite. Repair only thin labels. Optional disagreement metric OK.

**Rationale:** Never invent; API already supplied a label; silent overwrite would hide feed truth.

## Decision 14 — Pre-cutover tape retention

**Decision:** Keep rows allowed; analysis filters by cutover; delete optional later.

## Decision 15 — Cutover uses observed/insert time

**Decision:** Confirmed operator accept — KPI/repair population keyed off collector observed/insert time ≥ `repair_enabled_at`.

## Decision 16 — Template before Decision; no model-invented templates (2026-11-24)

**Decision:** Lookup order remains override → series → allowlisted deterministic template match → Decisions. Template match always precedes Decision. Decisions answers regime for **this market** only; write-through to **series** cache when `seriesSlug` present. Model MUST NOT generate or auto-promote new template ids. Template allowlist may be small or empty in A1.

**Rationale:** Avoid wasting model spend on unstable template invention; series + per-market Decision suffice when templates are weak.

**Alternatives considered:** Model invents template keys on miss (rejected); skip template step entirely (optional later if allowlist stays empty—but keep the slot for deterministic reuse).

## Decision 17 — Concrete allowlist + dumb normalizer (2026-11-24)

**Decision:** Lock seed allowlist to three ids from Data.md examples: `CRYPTO_UP_OR_DOWN_WINDOW` → `never_early`; `SPORTS_MATCHUP_WINNER` → `always_latent`; `EARNINGS_BEAT_EPS` → `always_latent`. Normalizer = lowercase/slot dates-money + ordered “all-of” cue rules; first match wins; ambiguity → miss. Cache miss on matched id seeds from allowlist default regime. No awards/`windowed` template in the reserved allowlist. Spec: `contracts/knowability-templates.md`.

**Rationale:** Operator asked for a clear, small, non-LLM definition; expandable only via versioned allowlist bump.

**Amendment 2026-11-25:** Product stamp is `knowability.templates.v1` (planning formerly called this `a1.v1`). Policy stamp is `knowability.v1`.

## Decision 18 — Disable cue matching (2026-11-24)

**Decision:** Ship with **matching disabled** (`match_template` always misses). Reserved ids remain for a future `knowability.templates.v2`+ bump. Lookup slot stays: override → series → template(miss) → Decisions.

**Rationale:** Operator — cue matching covers little of the market universe and false-positive regime stamps are worse than falling through to series/Decisions. Contract already allowed empty allowlist / disable.

**Amendment 2026-11-25:** Product short-circuits the template step via `TEMPLATE_MATCHING_ENABLED=false` (no automatic match / template-cache seed).
