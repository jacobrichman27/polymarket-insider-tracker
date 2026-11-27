"""Lifetime hydrate status and lifetime_is_first_trade rules."""

from __future__ import annotations

from polymarket_insider_tracker.ingestor.archive.wallet_hydrate import lifetime_is_first_trade_value


def test_lifetime_is_first_trade_only_on_complete_empty() -> None:
    assert lifetime_is_first_trade_value(complete=True, empty_walk=True) is True
    assert lifetime_is_first_trade_value(complete=True, empty_walk=False) is None
    assert lifetime_is_first_trade_value(complete=False, empty_walk=True) is None
