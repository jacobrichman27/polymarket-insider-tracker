# Polymarket Insider Tracker

**A research monitor for suspicious-looking trades on [Polymarket](https://polymarket.com).**

[![CI](https://github.com/pselamy/polymarket-insider-tracker/actions/workflows/ci.yml/badge.svg)](https://github.com/pselamy/polymarket-insider-tracker/actions/workflows/ci.yml)
[![Python 3.11–3.13](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Polymarket is a public prediction market. This project watches its public trade feed, looks up wallets on the Polygon blockchain, scores trades that look unusually informed (for example a brand-new wallet taking a large position in a quiet market), optionally saves those assessments, and can send alerts to Discord or Telegram.

**“Insider” here means heuristic suspicion, not proof of wrongdoing.** The tool is for transparency and research. It does not place trades, give financial advice, or claim that a flagged wallet broke any law.

No Polymarket API key is required. Trade and CLOB endpoints used by the tracker are public and anonymous.

---

## Who this is for

- **Operators** who want near-real-time alerts on unusual Polymarket activity
- **Researchers** who want a durable log of risk assessments for later analysis
- **Contributors** working from the Spec Kit slices under `specs/` (see [Contributing](#contributing))

---

## What it does

| Step | What happens |
|------|----------------|
| **Ingest** | Polls Polymarket’s documented public trades API (Data API v2) every few seconds |
| **Profile** | Looks up the trading wallet on Polygon (age, transaction count, optional funding trail) |
| **Detect** | Scores live signals: fresh wallets and size/niche anomalies (see [What it detects](#what-it-detects)) |
| **Persist** | Writes every signal-bearing assessment to PostgreSQL (on by default) |
| **Alert** | Optionally notifies Discord and/or Telegram when the score clears the alert threshold |
| **Observe** | Serves `/live`, `/ready`, `/health`, and Prometheus `/metrics` |

**What it does not do**

- Execute or recommend trades
- Require Discord/Telegram (alerts are optional; start with `--dry-run`)
- Guarantee a complete trade history — Redis keeps a short “how far we got” checkpoint; long outages can produce recorded loss events

---

## Prerequisites

| Tool | Why you need it |
|------|-----------------|
| **Python 3.11, 3.12, or 3.13** | Runtime (3.10 and 3.14+ are rejected by project metadata) |
| **[uv](https://docs.astral.sh/uv/) 0.11.x** (`>=0.11,<0.12`) | Locked installs via the checked-in `uv.lock`. CI uses **0.11.26**; uv 0.12+ will fail the project pin |
| **Docker with Compose** | Local PostgreSQL 15 and Redis 7 |
| **[mise](https://mise.jdx.dev/)** (optional for first run) | Pins security scanners and uv 0.11.26 (`mise.toml` / `mise.lock`). Needed for the Relentless security gate |

**Supported platforms:** Ubuntu 24.04 x86_64 is the blocking Linux reference. Apple Silicon macOS (`arm64`) is supported with advisory automation and local Docker-based evidence.

---

## Quick start (under 5 minutes)

This path installs dependencies and verifies local Postgres/Redis. It does **not** call Polymarket, Polygon, Discord, or Telegram until the final “start the tracker” step.

### 1. Clone and install

```bash
git clone https://github.com/pselamy/polymarket-insider-tracker.git
# or: git clone https://github.com/<you>/polymarket-insider-tracker.git
cd polymarket-insider-tracker
uv sync --locked --all-extras
```

The checked-in `uv.lock` is the source of truth for dependencies. Editable `pip install -e .` is a convenience only and is not treated as verification evidence.

### 2. Configure

```bash
cp .env.example .env
# Edit .env only if loopback ports or the default Postgres password conflict on your machine.
```

The app and Alembic both use one Psycopg 3 URL (already set in `.env.example`):

```text
postgresql+psycopg://tracker:dev_password@localhost:5432/polymarket_tracker
```

### 3. Start Postgres and Redis

```bash
docker compose up -d --wait postgres redis
docker compose ps
```

Optional admin UIs (note: Adminer’s default host port is **8080**, same as the tracker’s health port — change one if you run both):

```bash
docker compose --profile tools up -d
```

### 4. Probe services and check migrations safely

```bash
uv run --env-file .env python scripts/runtime_services.py --phase all
```

This checks Postgres and Redis, then runs upgrade → downgrade → upgrade on a **temporary** database. It never downgrades or drops the application database named in `.env`.

### 5. Migrate the app database and run

```bash
uv run --env-file .env alembic upgrade head
uv run --env-file .env python -m polymarket_insider_tracker --config-check
# First live-ish run without sending alerts:
uv run --env-file .env python -m polymarket_insider_tracker --dry-run
# Production-style run (contacts Polymarket + Polygon; sends alerts if configured):
uv run --env-file .env python -m polymarket_insider_tracker
```

Optional live-only smoke test of the trades API (not part of CI):

```bash
uv run --env-file .env python scripts/trades_smoke.py --live --window-seconds 5 --json
```

Full local verification gate:

```bash
uv run --env-file .env python scripts/verify.py --profile all
```

Profiles: `static`, `compatibility`, `services`, or `all` (see [Development](#development)).

---

## Alerts (optional)

Leave alert variables empty to run without notifications. Risk assessments can still be stored in Postgres.

| Channel | What to set |
|---------|-------------|
| **Discord** | `DISCORD_WEBHOOK_URL` — a channel webhook URL (treat it as a secret) |
| **Telegram** | Both `TELEGRAM_BOT_TOKEN` (from [BotFather](https://t.me/BotFather)) and `TELEGRAM_CHAT_ID` |

Prefer `--dry-run` (or `DRY_RUN=true`) until you are ready: the pipeline still scores and can persist assessments with `delivery_disposition="dry_run"`, but it sends **no** notifications and writes **no** Redis delivery-dedup keys.

### Research trades tape (opt-in)

`ARCHIVE_ENABLED` defaults to **off** so upgrades stay monitor-only. When you turn it on (after migrating to head):

1. Set `ARCHIVE_ENABLED=true` (keep `ARCHIVE_RAW_RETENTION=true` unless a versioned cost amendment says otherwise).
2. Restart; `/ready` gains a `trade_archive` component. First successful archive-enabled collection stamps durable `archive_start_at`.
3. Dry-run **still writes** the `trades` tape and gap ledger; it only suppresses real Discord/Telegram delivery.

Capacity assumptions (daily partitions, ~90-day primary retain/detach, raw-on disk budget, disk ≥70% ops alarm) live in `specs/005-research-trade-archive/quickstart.md` and `Data.md` Provisional capacity.

### Versioned markets & outcome repair (opt-in)

Archive-on warms append-on-change `markets` and knowability caches; it does **not** enable outcome repair by itself.

1. Keep `ARCHIVE_OUTCOME_REPAIR_ENABLED=false` until you want analysis-eligible inserts. Turning it on (with archive on) stamps durable `repair_enabled_at` once; only rows with observed/insert time ≥ cutover enter repair/KPI.
2. Knowability model-on-miss defaults intent-on (`ARCHIVE_KNOWABILITY_MODEL_ENABLED=true`) but is **effective only** when `ARCHIVE_KNOWABILITY_MODEL_API_KEY` is set; force off with `false`. Daily UTC budget defaults to 10000 Decisions calls (`gpt-6-luna`). Template allowlist version `knowability.templates.v1` reserves three ids but **cue matching is disabled** (prefer miss → series/Decisions).
3. Repair KPI may surface an optional `outcome_repair` diagnostic; it must **not** alone mark `trade_archive` down or fail `/ready`.
4. Primary win/loss analysis joins should require `outcome_repair_status` ∈ {`ok`, `not_needed`} (or an explicit unrepaired sensitivity stratum). This archive layer does not implement labels.

When delivery is enabled:

- Dedup is **per channel** (`alert:dedup:<channel>:<wallet>:<market>`), so a failed Discord send can still retry while Telegram already succeeded.
- A short ambiguity window suppresses duplicate sends while a delivery outcome is unknown (timeouts / concurrent dispatch).

---

## CLI options

```bash
uv run --env-file .env python -m polymarket_insider_tracker --help
```

| Flag | Meaning |
|------|---------|
| `--version` | Print version and exit |
| `--config-check` | Validate configuration offline and exit |
| `--log-level DEBUG` | Override `LOG_LEVEL` |
| `--dry-run` | Run the pipeline without sending alerts or writing delivery dedup keys |
| `--health-port 8080` | Override the health HTTP port (`HEALTH_PORT`) |

---

## Health and metrics

While running, the tracker serves HTTP endpoints on `--health-port` (default **8080**):

| Path | Purpose |
|------|---------|
| `/live` | Process is up (`{"live": true}`) |
| `/ready` | Postgres, Redis, and trade acquisition can make progress (503 when a required dependency is down, ingestion has failed terminally, or the trade source is stale) |
| `/health` | Detailed component status, latencies, quiet-period hints, and `last_error` (secrets redacted) |
| `/metrics` | Prometheus metrics (`polymarket_*` stream/health gauges; ingest metrics use `polymarket_ingest_*`) |

A recoverable `degraded` trade source with recent successful fetches can still be ready; details appear in `/health`.

---

## Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DATABASE_URL` | Yes | — | PostgreSQL URL (`postgresql+psycopg://…`) |
| `REDIS_URL` | No | `redis://localhost:6379` | Redis URL |
| `POLYGON_RPC_URL` | No | `https://polygon-rpc.com` | Polygon JSON-RPC (public default works; rate-limited) |
| `POLYGON_FALLBACK_RPC_URL` | No | — | Fallback RPC |
| `POLYMARKET_TRADES_URL` | No | `https://data-api.polymarket.com/v2/trades` | Public trades query (v2). Official v1 URL is rejected |
| `POLYMARKET_TRADES_COVERAGE` | No | `all` | `all` participants, or `taker-only` |
| `POLYMARKET_TRADES_POLL_INTERVAL_SECONDS` | No | `5` | Seconds between poll cycles (1–60) |
| `POLYMARKET_TRADES_RECOVERY_HORIZON_SECONDS` | No | `600` | How long Redis retains identities / detects loss (60–3600); **not** a completeness guarantee |
| `POLYMARKET_WS_URL` | No | — | **Deprecated** — accepted only as `ws://`/`wss://`, warns, never used |
| `POLYMARKET_API_KEY` | No | — | **Deprecated** — accepted with a warning, ignored (no credential is sent) |
| `DISCORD_WEBHOOK_URL` | No | — | Discord webhook for alerts |
| `TELEGRAM_BOT_TOKEN` | No | — | Telegram bot token (needs `TELEGRAM_CHAT_ID`) |
| `TELEGRAM_CHAT_ID` | No | — | Telegram chat for alerts |
| `DETECTOR_ALERT_THRESHOLD` | No | `0.80` | Minimum composite score to send an alert (0–1) |
| `DETECTOR_DEDUP_WINDOW_SECONDS` | No | `3600` | Per-(wallet, market) alert dedup window |
| `DETECTOR_PERSIST_ASSESSMENTS` | No | `true` | Persist every signal-bearing risk assessment |
| `ARCHIVE_ENABLED` | No | `false` | Opt-in research trades tape (fan-out + policy-(a) stall + `trade_archive` ready) |
| `ARCHIVE_RAW_RETENTION` | No | `true` | Store Core hot `raw_row_json` when archive is on (off only via versioned cost change) |
| `ARCHIVE_OUTCOME_REPAIR_ENABLED` | No | `false` | Forward-only async outcome repair (requires archive on) |
| `ARCHIVE_OUTCOME_REPAIR_LAG_SECONDS` | No | `300` | Post-cutover thin `not_attempted` lag KPI |
| `ARCHIVE_OUTCOME_REPAIR_UNREPAIRED_MAX_RATIO` | No | `0.05` | Unrepaired ceiling among thin post-cutover rows |
| `ARCHIVE_KNOWABILITY_MODEL_ENABLED` | No | `true` | Model-on-miss intent; `false` forces off |
| `ARCHIVE_KNOWABILITY_MODEL_MAX_CALLS_PER_DAY` | No | `10000` | Hard UTC-day Decisions call budget |
| `ARCHIVE_KNOWABILITY_MODEL_API_KEY` | No | — | OpenAI Decisions API key (secret; absent → model off) |
| `ARCHIVE_FEATURING_ENABLED` | No | `false` | Featured enrichment workers (requires archive on) |
| `ARCHIVE_FEATURING_NOTIONAL_CUTOFF_USDC` | No | `5000` | Versioned notional gate for featuring |
| `ARCHIVE_FEATURING_UNKNOWN_OPT_IN` | No | `false` | Opt `unknown` into featuring only via explicit bump |
| `ARCHIVE_CLASSIFIER_CONTROL_SAMPLE_RATE` | No | `0.001` | Seeded sample of `no_private_edge` for classifier control |
| `ARCHIVE_HOT_WINDOW_DAYS` | No | `14` | Hot window for regime-upgrade featuring backfill (7–30) |
| `ARCHIVE_ENRICHMENT_BUDGET_VERSION` | No | `b.v1` | Enrichment cap / status version stamp |
| `ARCHIVE_FINGERPRINT_VERSION` | No | `b.v2` | Strong/weak fill fingerprint version (canonical weak decimals) |
| `LOG_LEVEL` | No | `INFO` | Logging level |
| `DRY_RUN` | No | `false` | Skip sending alerts (same idea as `--dry-run`) |
| `HEALTH_PORT` | No | `8080` | Health / metrics HTTP port |

Compose also reads `POSTGRES_*`, `REDIS_HOST` / `REDIS_PORT`, `ADMINER_PORT`, and `REDIS_INSIGHT_PORT` for containers — see `.env.example`.

---

## How trade ingestion works

The tracker **polls** the public trades HTTP API; it does not use a live WebSocket feed (`POLYMARKET_WS_URL` is deprecated and unused).

In plain terms, each cycle:

1. Requests one page of recent trades (up to 10,000 rows) with a strictly advancing time cutoff so shared caches cannot return a stale page.
2. Validates rows, drops exact duplicates, and feeds **new** observations into the pipeline oldest-first.
3. Advances a durable “complete-through” checkpoint in Redis only when the page can be proven continuous with what was already seen.
4. If continuity cannot be proven, tries one documented recovery page; if that still fails, enters a visible `possible-data-loss` state (checkpoint frozen, new trades may still flow). Gaps that age past the recovery horizon are recorded as durable loss events.

Default poll interval is 5 seconds (~1% of the provider’s published rate limit). Market metadata is enrichment for detection; acquisition does **not** wait for the metadata crawl to finish.

Ingestion status appears in logs and `/health` (`running`, `degraded`, `possible-data-loss`, `failed`).

---

## What it detects

**Live scoring** (wired into the running pipeline) combines:

| Signal | Idea | Typical thresholds |
|--------|------|--------------------|
| **Fresh wallet** | New or lightly used wallet making a large trade | Age under ~48h, few lifetime txs, notional above a minimum |
| **Size / niche anomaly** | Trade large vs recent volume or the book; quiet markets weigh more | ~2% of 24h volume / book impact; niche markets (&lt; ~$50k daily) get a risk multiplier |

Composite score uses fixed default weights (alert threshold **0.80**, overridable via `DETECTOR_ALERT_THRESHOLD`). Multiple signals add bonuses (2 signals +20%, 3+ +30%). Every stored assessment records `scoring_algorithm_version` and the exact `scoring_config` used so it can be replayed later.

**Enrichment (not live score drivers by themselves)**

| Feature | Role today |
|---------|------------|
| **Funding chain** | On-chain trail toward known entities (e.g. exchange hot wallets); persisted for research when a fresh wallet is found |
| **Sniper clusters** | Experimental clustering helpers exist in the library; they are **not** part of the live alert path |

### Sample alert

```
SUSPICIOUS ACTIVITY DETECTED

Wallet: 0x7a3...f91 (Age: 2 hours, 3 transactions)
Market: "Will X announce Y by March 2026?"
Action: BUY YES @ $0.075
Size: $15,000 USDC (8.2% of daily volume)

Risk Signals:
  [x] Fresh Wallet (fewer than 5 transactions lifetime)
  [x] Niche Market (less than $50k daily volume)
  [x] Large Position (more than 2% order book impact)

Funding Trail:
  --> 0xdef...789 (2-year-old wallet, 500+ txns)
      --> Binance Hot Wallet

Confidence: HIGH (3/4 signals triggered)
```

---

## Architecture

```
Public trades API ──► Ingestor ──► Profiler ──► Detector ──► Alerter
   (HTTP poll)         (poller)    (Polygon)    (score)     (Discord/TG)
                           │                         │
                      Redis checkpoint          PostgreSQL
```

### Package map (`src/polymarket_insider_tracker/`)

| Module | Role |
|--------|------|
| `ingestor/` | Trade poller, Redis boundary / loss detection, CLOB + market metadata clients |
| `profiler/` | Polygon wallet analysis and funding tracing |
| `detector/` | Fresh-wallet and size/niche detectors, composite scorer |
| `alerter/` | Discord / Telegram dispatch and channel-scoped dedup |
| `storage/` | SQLAlchemy models, repositories, Alembic-backed schema |
| `pipeline.py` | Wires ingest → detect → persist → alert |
| `shutdown.py` | Graceful SIGTERM / SIGINT handling |

### Repository layout

| Path | Contents |
|------|----------|
| `src/` | Application package |
| `tests/` | Unit and integration tests (no `unittest.mock`; see Spec contracts) |
| `scripts/` | `verify.py`, `runtime_services.py`, `trades_smoke.py`, quality helpers |
| `alembic/` | Database migrations |
| `specs/` | Spec Kit feature slices and audit gap register |
| `quality/` | Relentless CI / security enrollment |
| `docs/` | Security gate notes, dependency upgrades, Relentless adoption |
| `docker-compose.yml` | Postgres, Redis, optional Adminer / RedisInsight |
| `mise.toml` | Pinned CLI tools for security and Relentless gates |

---

## Development

```bash
uv run python scripts/verify.py --profile static
uv run python scripts/verify.py --profile compatibility
uv run --env-file .env python scripts/verify.py --profile services
uv run --env-file .env python scripts/verify.py --profile all
```

| Profile | Checks |
|---------|--------|
| `static` | Lockfile, Black, Ruff, mypy, Pyright, Vulture, Complexipy / cyclomatic gates |
| `compatibility` | Locked imports and the deterministic test suite |
| `services` | Live local Postgres/Redis probes, disposable migration cycle, Redis behavioral contract |

Unit tests prefer real values and working fakes over `unittest.mock` (an AST policy rejects that framework). Redis in unit tests uses `fakeredis`; the `services` profile proves parity against real Redis. Only external boundaries (alert channels, CLOB SDK, Polygon RPC, webhooks) are faked.

Pyright is an extra checker on top of mypy (canonical production package, Python 3.11). Vulture and Complexipy (max cognitive complexity 5) cover every tracked repository Python file under `src`, `tests`, `scripts`, `alembic`, and `conftest.py`.

Relentless / security (needs **mise**):

```bash
mise install
uv run --locked --group dev python -m quality.verify
# or security scanners alone:
uv run --locked --group dev python -m quality.security_main
```

Details: [docs/security.md](docs/security.md).

### Docker services

| Service | Port | Notes |
|---------|------|-------|
| PostgreSQL 15 | 5432 | Primary database |
| Redis 7 | 6379 | Ingest checkpoints, dedup, caching |
| Adminer | 8080 | Optional (`--profile tools`) — conflicts with default `HEALTH_PORT` |
| RedisInsight | 5540 | Optional (`--profile tools`) |

---

## Contributing

Behavior changes are driven by Spec Kit slices under `specs/`. Start with [AGENTS.md](AGENTS.md) and [specs/README.md](specs/README.md).

Before any per-slice Spec Kit command, activate the intended directory explicitly (do not rely on ignored local pointer files):

```bash
SPECIFY_FEATURE_DIRECTORY=specs/002-reproducible-runtime .specify/scripts/bash/check-prerequisites.sh --json --require-tasks --include-tasks
```

Suggested slice order: `002` → `001` → `003` → `004`. Domain checklists are human-reviewer-owned.

---

## Troubleshooting

**No trades received**  
Check ingestion state in the logs. `degraded` means transient provider failures with backoff; `failed` means a terminal HTTP/body problem that needs a config or provider-contract fix. A quiet market shows `last_success_at` advancing while `last_trade_at` does not. Run `scripts/trades_smoke.py --live` to confirm reachability and schema.

**`possible-data-loss` in the logs**  
Two full pages could not prove continuity to the Redis checkpoint (often more than ~20,000 rows since the boundary). Monitoring continues with a frozen boundary; after the recovery horizon, a loss event is recorded and the boundary re-anchors. Investigate the recorded interval rather than assuming full coverage.

**`POLYMARKET_WS_URL` / `POLYMARKET_API_KEY` deprecation warnings**  
Remove them. Configure `POLYMARKET_TRADES_*` only; no API key is used.

**Connection / DNS errors**  
Confirm `https://data-api.polymarket.com` is reachable from your network.

**Database migration errors**  
Ensure `docker compose ps` shows healthy Postgres and that `.env` has a loopback `postgresql+psycopg://` `DATABASE_URL` matching Compose credentials. Run `uv run --env-file .env python scripts/runtime_services.py --phase probe`, then `alembic upgrade head`. Bare `postgresql://` and legacy `postgresql+asyncpg://` URLs are temporarily normalized with a deprecation warning; migrate to the Psycopg spelling. Asyncpg-specific query options are rejected before connect.

**Rate limiting on Polygon RPC**  
The default public RPC is limited. For heavier use, set `POLYGON_RPC_URL` to a dedicated provider (Alchemy, QuickNode, etc.).

**`uv` version errors**  
Use uv 0.11.x. `mise install` installs the pinned 0.11.26 tool if you use mise.

**Port 8080 already in use**  
Either stop Adminer (`docker compose --profile tools …`) or set `HEALTH_PORT` / `--health-port` to something else.

---

## Security notes

- Never log secrets or credential-bearing URLs; redaction is enforced in health output and logging filters.
- Exercise migration downgrades only on disposable databases (`scripts/runtime_services.py`), never on the configured app DB.
- Dry-run must not poison real delivery deduplication state.
- The Relentless security gate (`python -m quality.security_main`) runs opengrep, gitleaks, and osv-scanner with no allowlists — see [docs/security.md](docs/security.md).

---

## Disclaimer

This software is provided for **educational and research purposes only**.

- Trading prediction markets involves significant financial risk
- This tool does not constitute financial advice
- Detection signals are evidence for investigation, not proof of illegal insider trading
- Users are responsible for compliance with applicable laws

## License

MIT License — see [LICENSE](LICENSE) for details.
