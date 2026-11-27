"""Focused contract tests for knowability golden helpers (not the eval set)."""

from __future__ import annotations

from pathlib import Path

import pytest

from polymarket_insider_tracker.ingestor.archive.knowability_golden import (
    FixedDecisionsClient,
    GoldenCase,
    GoldenPrediction,
    classify_question_standalone,
    evaluate_case,
    load_golden_cases,
    offline_decisions_for,
    summarize_results,
    write_last_run,
)

REPO = Path(__file__).resolve().parents[2]
GOLDEN_V1 = REPO / "evals" / "knowability" / "golden.v1.jsonl"


def test_load_golden_v1_has_active_title_and_model_cases() -> None:
    cases = load_golden_cases(GOLDEN_V1)
    assert len(cases) >= 20
    assert any(case.expected_path == "title_rule" for case in cases)
    assert any(case.expected_path == "model" for case in cases)
    assert any(case.status == "provisional" for case in cases)


def test_golden_v1_includes_generalization_probes() -> None:
    cases = load_golden_cases(GOLDEN_V1)
    probes = [case for case in cases if case.id.startswith("gen-")]
    assert len(probes) >= 8
    assert any(case.expected_regime == "no_private_edge" for case in probes)
    assert any(case.expected_regime == "private_edge_possible" for case in probes)
    assert all(case.expected_path == "model" for case in probes)
    assert all(case.source == "generalization probe" for case in probes)


@pytest.mark.asyncio
async def test_standalone_title_rule_skips_decisions() -> None:
    stub = FixedDecisionsClient(regime="private_edge_possible", confidence=0.99)
    prediction = await classify_question_standalone(
        question="Will the highest temperature in Paris be 2°C?",
        series_slug=None,
        market_json=None,
        decisions=stub,
    )
    assert prediction.regime == "no_private_edge"
    assert prediction.label_source == "title_rule"


@pytest.mark.asyncio
async def test_standalone_model_path_uses_stub() -> None:
    stub = FixedDecisionsClient(regime="private_edge_possible", confidence=0.9)
    prediction = await classify_question_standalone(
        question="Broncos vs. Steelers",
        series_slug=None,
        market_json=None,
        decisions=stub,
    )
    assert prediction.regime == "private_edge_possible"
    assert prediction.label_source == "model"
    assert prediction.confidence == 0.9


@pytest.mark.asyncio
async def test_offline_evaluate_title_rule_case_from_set() -> None:
    cases = load_golden_cases(GOLDEN_V1)
    case = next(row for row in cases if row.id == "title-ou-total-001")
    prediction = await classify_question_standalone(
        question=case.question,
        series_slug=case.series_slug,
        market_json=case.market_json,
        decisions=offline_decisions_for(case),
    )
    result = evaluate_case(case, prediction, include_provisional=False)
    assert result.passed
    assert not result.skipped


def test_provisional_skipped_unless_included() -> None:
    case = GoldenCase(
        id="prov-1",
        question="Synthetic provisional?",
        expected_regime="no_private_edge",
        expected_path="model",
        status="provisional",
    )
    prediction = GoldenPrediction(regime="private_edge_possible", label_source="model")
    skipped = evaluate_case(case, prediction, include_provisional=False)
    assert skipped.skipped
    assert skipped.passed
    scored = evaluate_case(case, prediction, include_provisional=True)
    assert not scored.skipped
    assert not scored.passed


def test_summarize_results_lists_failures() -> None:
    case = GoldenCase(
        id="fail-1",
        question="Q",
        expected_regime="no_private_edge",
        expected_path="model",
    )
    prediction = GoldenPrediction(regime="private_edge_possible", label_source="model")
    result = evaluate_case(case, prediction, include_provisional=False)
    summary = summarize_results((result,))
    assert summary["failed"] == 1
    assert summary["failures"][0]["id"] == "fail-1"
    assert summary["by_expected_regime"]["no_private_edge"] == {
        "scored": 1,
        "passed": 0,
        "failed": 1,
    }
    assert summary["failures_by_expected_regime"]["no_private_edge"][0]["id"] == "fail-1"
    assert summary["by_predicted_regime"]["private_edge_possible"] == 1
    assert summary["cases"][0]["id"] == "fail-1"
    assert summary["cases"][0]["passed"] is False


def test_write_last_run_overwrites(tmp_path: Path) -> None:
    path = tmp_path / "last_run.json"
    write_last_run(path, {"passed": 1, "failed": 0})
    write_last_run(path, {"passed": 2, "failed": 1, "mode": "live"})
    payload = path.read_text(encoding="utf-8")
    assert '"passed": 2' in payload
    assert '"mode": "live"' in payload


def test_load_rejects_bad_regime(tmp_path: Path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text(
        '{"id":"x","question":"q","expected_regime":"nope","expected_path":"model"}\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="expected_regime"):
        load_golden_cases(path)
