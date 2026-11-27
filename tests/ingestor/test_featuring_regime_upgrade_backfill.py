"""Hot-window enqueue on regime upgrade."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from polymarket_insider_tracker.config import ArchiveSettings
from polymarket_insider_tracker.ingestor.archive.featuring import (
    hot_cutoff,
    is_still_hot,
)


def test_hot_window_uses_archive_hot_window_days() -> None:
    archive = ArchiveSettings(ARCHIVE_HOT_WINDOW_DAYS=14)
    now = datetime(2026, 11, 25, tzinfo=UTC)
    cutoff = hot_cutoff(now=now, hot_window_days=archive.hot_window_days)
    assert cutoff == now - timedelta(days=14)


def test_trade_exactly_at_hot_horizon_is_still_hot() -> None:
    now = datetime(2026, 11, 25, tzinfo=UTC)
    trade_ts = hot_cutoff(now=now, hot_window_days=14)
    assert is_still_hot(trade_ts=trade_ts, now=now, hot_window_days=14) is True


def test_trade_just_past_hot_horizon_is_not_hot() -> None:
    now = datetime(2026, 11, 25, tzinfo=UTC)
    trade_ts = hot_cutoff(now=now, hot_window_days=14) - timedelta(seconds=1)
    assert is_still_hot(trade_ts=trade_ts, now=now, hot_window_days=14) is False


def test_notional_gate_still_applies_for_backfill_trigger() -> None:
    from polymarket_insider_tracker.ingestor.archive.featuring import evaluate_featuring

    archive = ArchiveSettings(
        ARCHIVE_ENABLED=True,
        ARCHIVE_FEATURING_ENABLED=True,
        ARCHIVE_FEATURING_NOTIONAL_CUTOFF_USDC=5000,
    )
    decision = evaluate_featuring(
        archive=archive,
        regime="private_edge_possible",
        notional_usdc=Decimal("100"),
        observation_id="obs-small",
        trigger="regime_upgrade",
    )
    assert decision.eligible is False
