"""Featuring gate eligibility."""

from __future__ import annotations

from decimal import Decimal

from polymarket_insider_tracker.archive_defaults import DEFAULT_FEATURING_NOTIONAL_CUTOFF_USDC
from polymarket_insider_tracker.config import ArchiveSettings
from polymarket_insider_tracker.ingestor.archive.featuring import evaluate_featuring


def _archive(**overrides: object) -> ArchiveSettings:
    base: dict[str, object] = {
        "ARCHIVE_ENABLED": True,
        "ARCHIVE_FEATURING_ENABLED": True,
        "ARCHIVE_FEATURING_NOTIONAL_CUTOFF_USDC": DEFAULT_FEATURING_NOTIONAL_CUTOFF_USDC,
        "ARCHIVE_FEATURING_UNKNOWN_OPT_IN": False,
        "ARCHIVE_CLASSIFIER_CONTROL_SAMPLE_RATE": 0.0,
    }
    base.update(overrides)
    return ArchiveSettings.model_validate(base)


def test_private_edge_at_cutoff_is_eligible() -> None:
    decision = evaluate_featuring(
        archive=_archive(),
        regime="private_edge_possible",
        notional_usdc=Decimal("5000"),
        observation_id="obs-eligible",
    )
    assert decision.eligible is True
    assert decision.reason == "eligible"


def test_below_notional_is_excluded() -> None:
    decision = evaluate_featuring(
        archive=_archive(),
        regime="private_edge_possible",
        notional_usdc=Decimal("4999.99"),
        observation_id="obs-small",
    )
    assert decision.eligible is False
    assert decision.reason == "below_notional"


def test_unknown_excluded_when_opt_in_off() -> None:
    decision = evaluate_featuring(
        archive=_archive(),
        regime="unknown",
        notional_usdc=Decimal("10000"),
        observation_id="obs-unknown",
    )
    assert decision.eligible is False
    assert decision.reason == "regime_unknown"


def test_unknown_opt_in_allows_featuring() -> None:
    decision = evaluate_featuring(
        archive=_archive(ARCHIVE_FEATURING_UNKNOWN_OPT_IN=True),
        regime="unknown",
        notional_usdc=Decimal("10000"),
        observation_id="obs-unknown-opt",
    )
    assert decision.eligible is True
    assert decision.reason == "eligible"


def test_no_private_edge_excluded_when_sample_rate_zero() -> None:
    decision = evaluate_featuring(
        archive=_archive(ARCHIVE_CLASSIFIER_CONTROL_SAMPLE_RATE=0.0),
        regime="no_private_edge",
        notional_usdc=Decimal("10000"),
        observation_id="obs-control-off",
    )
    assert decision.eligible is False
    assert decision.reason == "regime_no_private_edge"


def test_classifier_control_sample_can_include_no_private_edge() -> None:
    decision = evaluate_featuring(
        archive=_archive(ARCHIVE_CLASSIFIER_CONTROL_SAMPLE_RATE=1.0),
        regime="no_private_edge",
        notional_usdc=Decimal("10000"),
        observation_id="obs-control-on",
    )
    assert decision.eligible is True
    assert decision.reason == "classifier_control"
    assert decision.trigger == "classifier_control"


def test_legacy_settlement_split_remains_eligible() -> None:
    decision = evaluate_featuring(
        archive=_archive(),
        regime="private_settlement_possible",
        notional_usdc=Decimal("5000"),
        observation_id="obs-settlement-legacy",
    )
    assert decision.eligible is True
    assert decision.reason == "eligible"


def test_legacy_factor_split_remains_eligible() -> None:
    decision = evaluate_featuring(
        archive=_archive(),
        regime="private_factor_possible",
        notional_usdc=Decimal("5000"),
        observation_id="obs-factor-legacy",
    )
    assert decision.eligible is True
    assert decision.reason == "eligible"
