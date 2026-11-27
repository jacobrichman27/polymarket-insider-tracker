# Knowability golden set

Frozen human-agreed market titles used to regress knowability judgment when
prompts, title rules, or policy stamps change.

**Not** collected by pytest. **Not** part of `scripts/verify.py` profiles or CI
(same isolation pattern as `scripts/trades_smoke.py`).

## Layout

| Path | Role |
| --- | --- |
| `golden.v1.jsonl` | Case set `knowability.golden.v1` |
| `last_run.json` | Overwritten baseline from the most recent runner invocation |
| `schema.md` | Field contract |
| `../../scripts/knowability_golden.py` | Runner |

## Run

Offline (default; no network, no credentials):

```bash
uv run python scripts/knowability_golden.py
```

Include provisional cases:

```bash
uv run python scripts/knowability_golden.py --include-provisional
```

Live Decisions (requires `ARCHIVE_KNOWABILITY_MODEL_API_KEY`; no DB/Redis writes):

```bash
uv run --env-file .env python scripts/knowability_golden.py --live
```

Exit `0` when all scored cases pass; `1` on mismatch; `2` on invocation error.

Each completed run overwrites `last_run.json` (aggregates + per-case rows, plus
`prompt_version` / `policy_version` / `captured_at`). Prefer refreshing with
`--live` so the baseline reflects Decisions, not offline stubs. Use
`--no-write-results` to print without overwriting; `--results-path` to redirect.

## When to bump the set

- Prompt/policy change that **preserves** judgment → keep `golden.v1.jsonl`; it should stay green offline and ideally live.
- Deliberate judgment change → append `golden.v2.jsonl` (or replace with a new set version) and note why here; do not silently rewrite history to hide regressions.

## Seeding

v1 seeds from the 2026-11-27 v8 uniform-random audit window, a couple of title_rule
smokes (full regex coverage stays in unit tests), and human disagrees on
season-accumulation props. Expand by appending rows; keep `id` stable.

**Generalization probes** (`id` prefix `gen-`): titles deliberately outside the
prompt’s named examples and title-cue vocabulary (no temperature / up-or-down /
tweets / O-U / spread / moneyline / awards / ballots wording). Offline still uses
recorded stubs; `--live` is what scores real Decisions generalization.
