#!/usr/bin/env python3
"""Run the knowability golden set (offline by default; optional --live).

Never part of ``scripts/verify.py`` profiles or CI. Offline uses title-rule plus
a fixed Decisions stub from each case. ``--live`` calls the Decisions API with
``ARCHIVE_KNOWABILITY_MODEL_API_KEY`` and never opens Redis or PostgreSQL.
Each completed run overwrites ``evals/knowability/last_run.json`` (baseline).
Exit: ``0`` all scored cases passed; ``1`` any mismatch; ``2`` invocation error.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from polymarket_insider_tracker.ingestor.archive.decisions_client import (
    KNOWABILITY_PROMPT_VERSION,
    DecisionsClient,
    HttpxDecisionsClient,
)
from polymarket_insider_tracker.ingestor.archive.knowability import (
    KNOWABILITY_POLICY_VERSION,
)
from polymarket_insider_tracker.ingestor.archive.knowability_golden import (
    GOLDEN_SET_VERSION,
    GoldenCase,
    GoldenCaseResult,
    classify_question_standalone,
    evaluate_case,
    load_golden_cases,
    offline_decisions_for,
    summarize_results,
    write_last_run,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SET = REPOSITORY_ROOT / "evals" / "knowability" / "golden.v1.jsonl"
DEFAULT_LAST_RUN = REPOSITORY_ROOT / "evals" / "knowability" / "last_run.json"
EXIT_PASSED = 0
EXIT_FAILED = 1
EXIT_USAGE = 2
API_KEY_ENV = "ARCHIVE_KNOWABILITY_MODEL_API_KEY"


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(list(argv) if argv is not None else None)
    cases = _load_or_usage(Path(args.set_path))
    if isinstance(cases, int):
        return cases
    results = _execute(cases, live=args.live, include_provisional=args.include_provisional)
    if isinstance(results, int):
        return results
    return _emit(
        results,
        live=args.live,
        set_path=Path(args.set_path),
        results_path=None if args.no_write_results else Path(args.results_path),
    )


def _load_or_usage(path: Path) -> tuple[GoldenCase, ...] | int:
    try:
        cases = load_golden_cases(path)
    except (OSError, ValueError) as exc:
        return _usage(str(exc))
    if not cases:
        return _usage("golden set is empty")
    return cases


def _execute(
    cases: tuple[GoldenCase, ...],
    *,
    live: bool,
    include_provisional: bool,
) -> tuple[GoldenCaseResult, ...] | int:
    if not live:
        return asyncio.run(_run_offline(cases, include_provisional=include_provisional))
    client = _live_client()
    if client is None:
        return _usage(f"--live requires {API_KEY_ENV}")
    return asyncio.run(_run_all(cases, client=client, include_provisional=include_provisional))


def _emit(
    results: tuple[GoldenCaseResult, ...],
    *,
    live: bool,
    set_path: Path,
    results_path: Path | None,
) -> int:
    summary = _build_summary(results, live=live, set_path=set_path)
    print(json.dumps(summary, indent=2, sort_keys=True))
    if results_path is not None:
        try:
            write_last_run(results_path, summary)
        except OSError as exc:
            return _usage(f"failed to write results: {exc}")
    if summary["failed"] == 0:
        return EXIT_PASSED
    return EXIT_FAILED


def _build_summary(
    results: tuple[GoldenCaseResult, ...],
    *,
    live: bool,
    set_path: Path,
) -> dict[str, Any]:
    summary = summarize_results(results)
    summary["captured_at"] = datetime.now(UTC).isoformat()
    summary["mode"] = "live" if live else "offline"
    summary["prompt_version"] = KNOWABILITY_PROMPT_VERSION
    summary["policy_version"] = KNOWABILITY_POLICY_VERSION
    summary["set_path"] = str(set_path)
    return summary


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            f"Knowability golden set ({GOLDEN_SET_VERSION}). "
            "Offline by default; never enrolled in verify.py / CI."
        )
    )
    parser.add_argument(
        "--set-path",
        default=str(DEFAULT_SET),
        help="JSONL golden set path (default: evals/knowability/golden.v1.jsonl)",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Call Decisions API (requires ARCHIVE_KNOWABILITY_MODEL_API_KEY)",
    )
    parser.add_argument(
        "--include-provisional",
        action="store_true",
        help="Score provisional cases (skipped by default)",
    )
    parser.add_argument(
        "--results-path",
        default=str(DEFAULT_LAST_RUN),
        help="Overwrite baseline JSON (default: evals/knowability/last_run.json)",
    )
    parser.add_argument(
        "--no-write-results",
        action="store_true",
        help="Print summary only; do not overwrite the baseline file",
    )
    return parser


def _live_client() -> HttpxDecisionsClient | None:
    api_key = (os.environ.get(API_KEY_ENV) or "").strip()
    if not api_key:
        return None
    return HttpxDecisionsClient(api_key=api_key)


async def _run_offline(
    cases: tuple[GoldenCase, ...],
    *,
    include_provisional: bool,
) -> tuple[GoldenCaseResult, ...]:
    return await _run_with_factory(cases, include_provisional=include_provisional, live_client=None)


async def _run_all(
    cases: tuple[GoldenCase, ...],
    *,
    client: DecisionsClient,
    include_provisional: bool,
) -> tuple[GoldenCaseResult, ...]:
    return await _run_with_factory(
        cases, include_provisional=include_provisional, live_client=client
    )


async def _run_with_factory(
    cases: tuple[GoldenCase, ...],
    *,
    include_provisional: bool,
    live_client: DecisionsClient | None,
) -> tuple[GoldenCaseResult, ...]:
    rows: list[GoldenCaseResult] = []
    for case in cases:
        decisions: DecisionsClient = live_client or offline_decisions_for(case)
        prediction = await classify_question_standalone(
            question=case.question,
            series_slug=case.series_slug,
            market_json=case.market_json,
            decisions=decisions,
        )
        rows.append(evaluate_case(case, prediction, include_provisional=include_provisional))
    return tuple(rows)


def _usage(message: str) -> int:
    print(message, file=sys.stderr)
    return EXIT_USAGE


if __name__ == "__main__":
    raise SystemExit(main())
