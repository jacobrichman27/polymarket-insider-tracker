"""trade_archive readiness SLO mapping."""

from __future__ import annotations

from polymarket_insider_tracker.ingestor.archive.health import (
    DEGRADED_OWED_SECONDS,
    DOWN_OWED_SECONDS,
    ArchiveHealthSignals,
)


def test_quiet_market_stays_up() -> None:
    signals = ArchiveHealthSignals()
    status = signals.evaluate(1_000.0)
    assert status.status == "up"


def test_owed_age_degraded_then_down() -> None:
    signals = ArchiveHealthSignals()
    signals.mark_owed("obs-1", 1_000.0)
    assert signals.evaluate(1_000.0 + DEGRADED_OWED_SECONDS + 1).status == "degraded"
    assert signals.evaluate(1_000.0 + DOWN_OWED_SECONDS + 1).status == "down"


def test_recent_failure_degrades() -> None:
    signals = ArchiveHealthSignals()
    signals.mark_attempt(1_000.0, failed=False)
    signals.mark_attempt(1_010.0, failed=True)
    assert signals.evaluate(1_030.0).status == "degraded"


def test_clear_owed_returns_up() -> None:
    signals = ArchiveHealthSignals()
    signals.mark_owed("obs-1", 1_000.0)
    signals.clear_owed("obs-1")
    assert signals.evaluate(1_400.0).status == "up"
