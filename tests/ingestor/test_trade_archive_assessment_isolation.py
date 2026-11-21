"""Assessment persist failure must not mark trade_archive down or block alerts (FR-013)."""

from __future__ import annotations

import logging

import pytest
from fakeredis import FakeAsyncRedis

from polymarket_insider_tracker.ingestor.archive.health import ArchiveHealthSignals
from polymarket_insider_tracker.storage.database import DatabaseManager
from tests.fakes import FakeAlertChannel, FakeEth, make_test_settings, wire_pipeline
from tests.integration._journey_harness import make_sample_trade_event, market_for_trade

UNREACHABLE_DATABASE_URL = "postgresql+psycopg://tracker:unused@127.0.0.1:1/unreachable"


@pytest.mark.asyncio
async def test_assessment_persist_failure_leaves_tape_up_and_delivers(
    fake_redis: FakeAsyncRedis,
    caplog: pytest.LogCaptureFixture,
) -> None:
    sample_trade = make_sample_trade_event()
    unreachable_db = DatabaseManager(UNREACHABLE_DATABASE_URL, async_mode=True)
    channel = FakeAlertChannel("discord")
    settings = make_test_settings(
        persist_assessments=True,
        alert_threshold=0.1,
        archive_enabled=True,
    )
    pipeline = await wire_pipeline(
        settings,
        redis=fake_redis,
        eth=FakeEth(transaction_count=2),
        market=market_for_trade(sample_trade, "science"),
        db_manager=unreachable_db,
        channels=[channel],
    )
    try:
        with caplog.at_level(logging.WARNING):
            await pipeline.process_trade(sample_trade)
        components = await pipeline.health_monitor.evaluate_components()
        tape = components["trade_archive"]
    finally:
        await unreachable_db.dispose_async()

    assert "Failed to persist risk assessment" in caplog.text
    assert len(channel.deliveries) == 1
    assert pipeline.stats.alerts_sent == 1
    assert tape.status == "up"
    # Direct signal model: assessment path never marks owed/failures on the tape.
    signals = ArchiveHealthSignals()
    assert signals.evaluate(1_000.0).status == "up"
