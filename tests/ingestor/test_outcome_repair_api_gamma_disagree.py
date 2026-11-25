"""Usable API outcome stays not_needed even if Gamma disagrees."""

from __future__ import annotations

from polymarket_insider_tracker.ingestor.archive.outcome_repair import decide_repair


def test_usable_api_not_overwritten_by_gamma_map() -> None:
    decision = decide_repair(
        outcome="Yes",
        outcome_index=0,
        token_id="tok",
        token_outcomes={"tok": {"outcome": "No", "outcome_index": 1}},
    )
    assert decision.status == "not_needed"
    assert decision.outcome_repaired is None
    assert decision.outcome_index_repaired is None
