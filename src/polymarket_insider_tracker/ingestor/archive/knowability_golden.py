"""Offline/live knowability golden-set helpers (not part of verify/CI).

Classify a frozen question through the same title-rule → Decisions order as
production, without Postgres caches or Redis. Used by
``scripts/knowability_golden.py`` and its focused unit tests.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast

from polymarket_insider_tracker.ingestor.archive.decisions_client import (
    TITLE_RULE_LABEL_SOURCE,
    DecisionsClient,
    DecisionsRegimeResult,
    no_edge_title_rule,
)
from polymarket_insider_tracker.ingestor.archive.knowability import (
    KNOWABILITY_POLICY_VERSION,
    VALID_REGIMES,
)

GOLDEN_SET_VERSION = "knowability.golden.v1"
LABEL_SOURCES = frozenset({"title_rule", "model", "unknown"})
CaseStatus = Literal["active", "provisional"]


@dataclass(frozen=True)
class GoldenCase:
    id: str
    question: str
    expected_regime: str
    expected_path: str
    family: str | None = None
    series_slug: str | None = None
    market_json: dict[str, Any] | None = None
    recorded_regime: str | None = None
    recorded_confidence: float | None = None
    rationale: str = ""
    source: str = ""
    set_version: str = GOLDEN_SET_VERSION
    status: CaseStatus = "active"
    min_policy: str = KNOWABILITY_POLICY_VERSION
    min_prompt: str = "knowability.prompt.v8"


@dataclass(frozen=True)
class GoldenPrediction:
    regime: str
    label_source: str
    confidence: float | None = None


@dataclass(frozen=True)
class GoldenCaseResult:
    case: GoldenCase
    prediction: GoldenPrediction
    regime_ok: bool
    path_ok: bool
    skipped: bool = False
    skip_reason: str | None = None

    @property
    def passed(self) -> bool:
        if self.skipped:
            return True
        return self.regime_ok and self.path_ok


@dataclass
class FixedDecisionsClient:
    """Returns a frozen Decisions answer (offline model-path cases)."""

    regime: str
    confidence: float | None = None

    async def classify_regime(
        self,
        *,
        question: str,
        series_slug: str | None,
        market_json: object | None,
    ) -> DecisionsRegimeResult:
        del question, series_slug, market_json
        return DecisionsRegimeResult(regime=self.regime, confidence=self.confidence)


async def classify_question_standalone(
    *,
    question: str,
    series_slug: str | None,
    market_json: object | None,
    decisions: DecisionsClient,
) -> GoldenPrediction:
    """Title-rule short-circuit, else Decisions — no DB/Redis."""
    if no_edge_title_rule(question) is not None:
        return GoldenPrediction(regime="no_private_edge", label_source=TITLE_RULE_LABEL_SOURCE)
    result = await decisions.classify_regime(
        question=question, series_slug=series_slug, market_json=market_json
    )
    regime = result.regime if result.regime in VALID_REGIMES else "unknown"
    source = "model" if regime != "unknown" else "unknown"
    return GoldenPrediction(regime=regime, label_source=source, confidence=result.confidence)


def load_golden_cases(path: Path) -> tuple[GoldenCase, ...]:
    """Parse JSONL golden cases; fail closed on malformed rows."""
    rows: list[GoldenCase] = []
    for line_no, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        text = raw.strip()
        if not text or text.startswith("#"):
            continue
        rows.append(_parse_case_line(text, line_no=line_no))
    return tuple(rows)


def _parse_case_line(text: str, *, line_no: int) -> GoldenCase:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"line {line_no}: invalid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"line {line_no}: case must be a JSON object")
    return _case_from_mapping(cast(dict[str, Any], payload), line_no=line_no)


def _case_from_mapping(payload: dict[str, Any], *, line_no: int) -> GoldenCase:
    case_id = _require_str(payload, "id", line_no=line_no)
    question = _require_str(payload, "question", line_no=line_no)
    expected_regime = _require_str(payload, "expected_regime", line_no=line_no)
    expected_path = _require_str(payload, "expected_path", line_no=line_no)
    _validate_regime(expected_regime, field="expected_regime", line_no=line_no)
    if expected_path not in LABEL_SOURCES:
        raise ValueError(f"line {line_no}: bad expected_path {expected_path!r}")
    status_raw = payload.get("status", "active")
    status = _parse_status(status_raw, line_no=line_no)
    recorded = payload.get("recorded_regime")
    if recorded is not None:
        if not isinstance(recorded, str):
            raise ValueError(f"line {line_no}: recorded_regime must be a string")
        _validate_regime(recorded, field="recorded_regime", line_no=line_no)
    return GoldenCase(
        id=case_id,
        question=question,
        expected_regime=expected_regime,
        expected_path=expected_path,
        family=_optional_str(payload.get("family")),
        series_slug=_optional_str(payload.get("series_slug")),
        market_json=_optional_mapping(payload.get("market_json"), line_no=line_no),
        recorded_regime=recorded,
        recorded_confidence=_optional_float(payload.get("recorded_confidence"), line_no=line_no),
        rationale=str(payload.get("rationale") or ""),
        source=str(payload.get("source") or ""),
        set_version=str(payload.get("set_version") or GOLDEN_SET_VERSION),
        status=status,
        min_policy=str(payload.get("min_policy") or KNOWABILITY_POLICY_VERSION),
        min_prompt=str(payload.get("min_prompt") or "knowability.prompt.v8"),
    )


def _parse_status(value: object, *, line_no: int) -> CaseStatus:
    if value == "active":
        return "active"
    if value == "provisional":
        return "provisional"
    raise ValueError(f"line {line_no}: bad status {value!r}")


def _require_str(payload: dict[str, Any], key: str, *, line_no: int) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"line {line_no}: {key} must be a non-empty string")
    return value.strip()


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _optional_float(value: object, *, line_no: int) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"line {line_no}: recorded_confidence must be a number")
    score = float(value)
    if score < 0.0 or score > 1.0:
        raise ValueError(f"line {line_no}: recorded_confidence out of range")
    return score


def _optional_mapping(value: object, *, line_no: int) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"line {line_no}: market_json must be an object")
    typed = cast(dict[str, Any], value)
    return {key: typed[key] for key in typed}


def _validate_regime(regime: str, *, field: str, line_no: int) -> None:
    if regime not in VALID_REGIMES:
        raise ValueError(f"line {line_no}: bad {field} {regime!r}")


def evaluate_case(
    case: GoldenCase,
    prediction: GoldenPrediction,
    *,
    include_provisional: bool,
) -> GoldenCaseResult:
    """Compare prediction to human expectations."""
    if case.status == "provisional" and not include_provisional:
        return GoldenCaseResult(
            case=case,
            prediction=prediction,
            regime_ok=True,
            path_ok=True,
            skipped=True,
            skip_reason="provisional",
        )
    return GoldenCaseResult(
        case=case,
        prediction=prediction,
        regime_ok=prediction.regime == case.expected_regime,
        path_ok=prediction.label_source == case.expected_path,
    )


def offline_decisions_for(case: GoldenCase) -> FixedDecisionsClient:
    """Stub Decisions with the case's recorded (or expected) regime."""
    regime = case.recorded_regime or case.expected_regime
    return FixedDecisionsClient(regime=regime, confidence=case.recorded_confidence)


def summarize_results(results: tuple[GoldenCaseResult, ...]) -> dict[str, Any]:
    """Aggregate pass/fail counts for the runner JSON summary."""
    scored = [row for row in results if not row.skipped]
    failed = [row for row in scored if not row.passed]
    return _assemble_summary(results, scored=scored, failed=failed)


def _assemble_summary(
    results: tuple[GoldenCaseResult, ...],
    *,
    scored: list[GoldenCaseResult],
    failed: list[GoldenCaseResult],
) -> dict[str, Any]:
    return {
        "set_version": GOLDEN_SET_VERSION,
        "total": len(results),
        "scored": len(scored),
        "skipped": len(results) - len(scored),
        "passed": len(scored) - len(failed),
        "failed": len(failed),
        "by_expected_regime": _stats_by_expected_regime(scored),
        "by_predicted_regime": _count_predicted(scored, kind="regime"),
        "by_path": _count_predicted(scored, kind="path"),
        "failures": [_failure_row(row) for row in failed],
        "failures_by_expected_regime": _failures_by_expected_regime(failed),
        "cases": [_case_row(row) for row in results],
    }


def write_last_run(path: Path, summary: dict[str, Any]) -> None:
    """Overwrite the baseline run file (fail closed on IO errors)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _count_predicted(rows: list[GoldenCaseResult], *, kind: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        key = row.prediction.regime if kind == "regime" else row.prediction.label_source
        counts[key] = counts.get(key, 0) + 1
    return counts


def _stats_by_expected_regime(rows: list[GoldenCaseResult]) -> dict[str, dict[str, int]]:
    stats: dict[str, dict[str, int]] = {}
    for row in rows:
        bucket = stats.setdefault(row.case.expected_regime, {"scored": 0, "passed": 0, "failed": 0})
        bucket["scored"] += 1
        if row.passed:
            bucket["passed"] += 1
        else:
            bucket["failed"] += 1
    return stats


def _failures_by_expected_regime(
    failed: list[GoldenCaseResult],
) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in failed:
        grouped.setdefault(row.case.expected_regime, []).append(_failure_row(row))
    return grouped


def _failure_row(row: GoldenCaseResult) -> dict[str, str]:
    return {
        "id": row.case.id,
        "expected_regime": row.case.expected_regime,
        "got_regime": row.prediction.regime,
        "expected_path": row.case.expected_path,
        "got_path": row.prediction.label_source,
    }


def _case_row(row: GoldenCaseResult) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": row.case.id,
        "expected_regime": row.case.expected_regime,
        "got_regime": row.prediction.regime,
        "expected_path": row.case.expected_path,
        "got_path": row.prediction.label_source,
        "passed": row.passed,
        "skipped": row.skipped,
        "confidence": row.prediction.confidence,
    }
    if row.skip_reason is not None:
        payload["skip_reason"] = row.skip_reason
    return payload
