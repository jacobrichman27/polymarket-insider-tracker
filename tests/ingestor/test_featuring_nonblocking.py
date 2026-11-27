"""Featuring evaluation is synchronous and does not await enrichment."""

from __future__ import annotations

from decimal import Decimal

from polymarket_insider_tracker.config import ArchiveSettings
from polymarket_insider_tracker.ingestor.archive.featuring import evaluate_featuring


def test_evaluate_featuring_returns_without_side_effects() -> None:
    archive = ArchiveSettings(ARCHIVE_ENABLED=True, ARCHIVE_FEATURING_ENABLED=True)
    decision = evaluate_featuring(
        archive=archive,
        regime="private_edge_possible",
        notional_usdc=Decimal("9000"),
        observation_id="obs-sync",
    )
    assert decision.eligible is True
    assert decision.reason == "eligible"
