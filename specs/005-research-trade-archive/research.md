# Research: Research Trade Archive (Phase A0)

**Feature**: `specs/005-research-trade-archive`  
**Date**: 2026-11-18  
**Input**: [spec.md](spec.md), amended [001 observation-boundary](../001-supported-trade-ingestion/contracts/observation-boundary.md), amended [003 health-endpoints](../003-safe-observable-operation/contracts/health-endpoints.md), root [`Data.md`](../../Data.md)

## Decision 1 — Reuse TradePoller; change delivery, not acquisition

**Decision:** Keep the existing 5s all-participant poll, Redis complete-through proof, and possible-data-loss path. Implement archive-enabled delivery inside `TradePoller` (fan-out driver) rather than a second global feed or parallel proof model.

**Rationale:** Slice 001 already owns acquisition correctness. Spec FR-020 and constitution V require consuming the amended boundary contract, not forking it. Gaps G-036–G-038 are handoff/retain bugs, not source bugs.

**Alternatives considered:**
- Separate archive poller / Redis namespace — rejected (duplicate load, divergent proof, unauthorized parallel model).
- Outbox + advance (policy b) — deferred; requires a later versioned 001 amendment.

## Decision 2 — Fan-out adapter with monitor-only default

**Decision:** Introduce an explicit fan-out delivery path when `ARCHIVE_ENABLED=true`: Archive → Monitor → reserved future slot. Default `ARCHIVE_ENABLED=false` preserves today’s retain-after-monitor semantics via the deprecation adapter. Monitor keeps `TradeEvent`-only in A0; Archive always receives full `TradeObservation` (extend with raw payload).

**Rationale:** Clarify session locked opt-in default off and event-only monitor. Matches constitution V upgrade safety and Data.md isolation matrix.

**Alternatives considered:**
- Default archive on — rejected in clarify (breaks existing monitor upgrades with stall/ready).
- Force full observation into Monitor in A0 — deferred; unnecessary monitor churn.

## Decision 3 — Hot-path idempotent Postgres insert (no outbox)

**Decision:** Archive consumer performs immediate idempotent `INSERT … ON CONFLICT DO NOTHING` (or equivalent) on `(trade_ts, observation_id)`. Success authorizes `record_identity`. Failure opens/updates `write_failure`, does not retain, stalls checkpoint, retries with bounded backoff; abandon when unreachable past recovery horizon.

**Provisional retry backoff (locked 2026-11-18, analyze U3):** initial delay **250 ms**, exponential ×2, cap **5 s** between attempts; keep retrying while the observation remains owed and reachable (horizon / acquisition reachability owns abandon—not a fixed attempt count). Jitter optional (±10%). Revise with ops evidence without changing policy (a).

**Rationale:** Policy (a) locked; markers-only rejected. Hot raw on the row is forensic, not the restore path.

**Alternatives considered:**
- Durable outbox reconciler — policy (b), not A0.
- Advance + marker only — rejected (permanent holes).

## Decision 4 — Schema: partitioned `trades` + `ingest_gap_events`; no fingerprint; no stored `data_complete`

**Decision:** Alembic migration adds:
- Parent `trades` partitioned by RANGE on `trade_ts` (daily UTC children, pre-create ahead).
- `ingest_gap_events` for `ingest_loss` and `write_failure`.
- Singleton durable `archive_collector_state` (or equivalent) holding `archive_start_at`.
Omit `fill_fingerprint` columns. Do not store windowed `data_complete` on rows. **Defer chain locator/fee columns to Phase B** (do not reserve a wide null-column set in A0).

**Rationale:** Clarify + Data.md A0 minimum. Fingerprint, locators, and derived completeness belong later; ledger is honesty input.

**Alternatives considered:**
- Unpartitioned `trades` — rejected (detach/capacity story for 90-day interim).
- Weak fingerprint “for convenience” — rejected in clarify.
- Nullable reserved locator columns in A0 — rejected 2026-11-18 (analyze U2); B adds columns when enrichment lands.

## Decision 5 — Section-1 A0 column set (API + cheap derived + status defaults)

**Decision:** Persist Core warm API/cheap fields at insert: identity, tx, trade_ts, observed_at, wallet, condition/token, raw outcome fields, side, price, size/notional, source, `archive_start_at`, provisional knowability `unknown` (nullable regime column or explicit default), `outcome_repair_status='not_attempted'` (or `not_needed` when API label already usable), `receipt_status='not_attempted'`, Core hot `raw_row_json` when raw retention on. Do **not** add locator/fee result columns in A0.

**Rationale:** Data.md A0 + outcome-repair quality init without blocking Gamma.

**Alternatives considered:**
- Block insert until Gamma repair — rejected (hard latency rule).
- Skip raw unless debug — rejected (Core unless versioned cost flag).

## Decision 6 — Config surface

**Decision:** Nested `ArchiveSettings` (env prefix `ARCHIVE_`):
- `ARCHIVE_ENABLED` bool default `false`
- `ARCHIVE_RAW_RETENTION` bool default `true` (disabling requires documented versioned cost amendment)
- Optional tuning: retry backoff bounds, owed-age metrics already feed health SLOs from 003 contract
`archive_start_at` is **not** a freely mutable env default for burn-in; first successful archive-enabled collection writes durable state; env may seed only when state is empty.

**Rationale:** Clarify FR-001/FR-016; mirrors `DETECTOR_PERSIST_ASSESSMENTS` pattern in `config.py`.

## Decision 7 — Health wiring reuses 003 HealthMonitor

**Decision:** When archive enabled, register a `trade_archive` component checker fed by archive writer metrics (oldest owed age, recent failure window). Monitor-only omits the component. Assessment persist failures stay off this component (IV).

**Rationale:** Amended 003 contract; G-041. No parallel log-only readiness.

## Decision 8 — Capacity assumptions (provisional, plan-owned)

**Decision:** Adopt Data.md provisional capacity as A0 plan defaults:
- Daily UTC partitions; pre-create ≥7 days ahead; alarm on missing partition
- Indexes: PK `(trade_ts, observation_id)`; `(condition_id, trade_ts)`; `(proxy_wallet, trade_ts)`; `(transaction_hash, trade_ts)`
- Interim retain ≈90 days on primary then detach (not silent delete)
- Growth input 5×10⁵–2×10⁶ rows/day; ~2.5–10 KiB/row with raw; safety ≥2
- Alarms: disk 70% budget; missing partition; insert rate 2× sizing; backlog tied to tape health

**Rationale:** G-043; Phase D may automate compaction but A0 must not ship unbounded primary growth.

**Alternatives considered:** Defer all sizing to Phase D — rejected.

## Decision 9 — Test strategy

**Decision:** Extend poller harness with injectable Archive consumer (success/fail/crash-between); FakeAsyncRedis + real ObservationBoundary; SQLite/Postgres disposable engines for insert idempotency and gap ledger; health component tests with fake clock for SLO thresholds. No `unittest.mock`. Prefer working fakes and real value objects per slice 002 test-quality contract. Services profile proves Alembic upgrade/downgrade on real Postgres.

**Rationale:** Constitution III + existing project AST policy.

## Decision 10 — Plane extensibility without execution code

**Decision:** Document reserved third consumer slot as a typed no-op / protocol in the fan-out driver. Do not ship order clients, wallets, or credentials. Leakage firewall stated in contracts: labels/features out of A0.

**Rationale:** Spec FR-018 / constitution I–II.

## Decision 11 — Dry-run vs archive tape (analyze U4)

**Decision:** When `ARCHIVE_ENABLED=true`, **dry-run still performs durable archive inserts** (and gap-ledger writes). Dry-run continues to suppress real Discord/Telegram delivery and must not poison delivery dedup—unchanged from slice 003. Research tape durability is independent of alert dry-run.

**Rationale:** Constitution IV targets notification side effects; the archive is the data plane. Skipping inserts in dry-run would leave operators without a safe way to exercise the tape.

**Alternatives considered:**
- Dry-run skips archive writes — rejected (hides tape bugs; undermines A0 acceptance in dry-run CI).
- Separate `ARCHIVE_DRY_RUN` — deferred; not needed for A0.

## Decision 12 — Capacity alarms in-process (analyze U1)

**Decision:** A0 exposes **Prometheus metrics + health-adjacent signals** for: missing partition / partition-miss failures, insert rate (for 2× sizing comparison), and owed backlog (already feeds `trade_archive`). Disk ≥70% of budget is an **ops/runbook alarm** documented in README/quickstart (process or host monitor), not a required in-process disk poller. Missing-partition and insert-rate signals MUST be testable in-process.

**Rationale:** FR-017/SC-008 need verifiable alarms without mandating host filesystem agents inside the app.
