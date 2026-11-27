"""Insert-time tape anomaly classification."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from polymarket_insider_tracker.ingestor.archive.tape_anomaly import (
    anomaly_counts,
    clear_anomaly_counts,
    observe_tape_observation,
)
from polymarket_insider_tracker.ingestor.trade_rows import TradeObservation, parse_trade_row
from tests.fakes.trades import trade_row

NOW = 1_788_983_720


def _base() -> TradeObservation:
    row = trade_row(timestamp=NOW - 5, transaction=42, wallet=7, price="0.55", size="100")
    parsed = parse_trade_row(row, now=NOW)
    assert isinstance(parsed, TradeObservation)
    return parsed


def test_thin_and_price_and_side_anomalies() -> None:
    clear_anomaly_counts()
    obs = _base()
    weird_event = replace(
        obs.event,
        outcome="",
        outcome_index=999,
        price=Decimal("1.5"),
        side="HOLD",
    )
    weird = replace(obs, event=weird_event, raw_row=None)
    observe_tape_observation(weird, raw_retention=False)
    counts = anomaly_counts()
    assert counts.get("thin_outcome", 0) >= 1
    assert counts.get("price_out_of_range", 0) >= 1
    assert counts.get("unexpected_side", 0) >= 1


def test_stale_and_missing_raw() -> None:
    clear_anomaly_counts()
    obs = _base()
    stale_ts = datetime.now(UTC) - timedelta(hours=2)
    stale = replace(obs, event=replace(obs.event, timestamp=stale_ts), raw_row=None)
    observe_tape_observation(stale, raw_retention=True, now=datetime.now(UTC))
    counts = anomaly_counts()
    assert counts.get("stale_trade_ts", 0) >= 1
    assert counts.get("missing_raw_row", 0) >= 1
