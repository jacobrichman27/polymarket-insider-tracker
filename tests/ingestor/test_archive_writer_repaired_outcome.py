"""Hot-path REPAIRED outcomes persist as ok + repaired fields."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from polymarket_insider_tracker.ingestor.archive.writer import _outcome_fields
from polymarket_insider_tracker.ingestor.models import TradeEvent
from polymarket_insider_tracker.ingestor.trade_rows import OutcomeResolution, TradeObservation


def _obs(*, resolution: OutcomeResolution, outcome: str, index: int) -> TradeObservation:
    event = TradeEvent(
        market_id="c1",
        trade_id="0xabc",
        wallet_address="0xwallet",
        side="BUY",
        outcome=outcome,
        outcome_index=index,
        price=Decimal("0.4"),
        size=Decimal("10"),
        timestamp=datetime(2026, 11, 26, 12, 0, tzinfo=UTC),
        asset_id="tok",
    )
    return TradeObservation(
        event=event,
        identity="obs",
        provider_timestamp=1,
        outcome_resolution=resolution,
        raw_row={"outcome": outcome, "outcomeIndex": 999},
    )


def test_repaired_resolution_writes_ok_and_keeps_api_columns_thin() -> None:
    outcome, index, status, repaired, repaired_index = _outcome_fields(
        _obs(resolution=OutcomeResolution.REPAIRED, outcome="Yes", index=0)
    )
    assert (outcome, index) == (None, None)
    assert status == "ok"
    assert repaired == "Yes"
    assert repaired_index == 0


def test_provided_resolution_is_not_needed() -> None:
    outcome, index, status, repaired, repaired_index = _outcome_fields(
        _obs(resolution=OutcomeResolution.PROVIDED, outcome="No", index=1)
    )
    assert (outcome, index, status) == ("No", 1, "not_needed")
    assert repaired is None and repaired_index is None
