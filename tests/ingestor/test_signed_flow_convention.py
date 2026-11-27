"""Convention-signed aggregates use API side on canonical leg."""

from __future__ import annotations

from polymarket_insider_tracker.ingestor.archive.signed_flow_kpi import convention_signed_side


def test_canonical_leg_uses_api_side() -> None:
    assert convention_signed_side(api_side="BUY", canonical_leg=True) == "BUY"
    assert convention_signed_side(api_side="BUY", canonical_leg=False) is None
