"""Checkpoint stall and bounded archive retry."""

from __future__ import annotations

import pytest
from fakeredis import FakeAsyncRedis

from polymarket_insider_tracker.config import PolymarketSettings
from polymarket_insider_tracker.ingestor.archive.delivery import (
    BACKOFF_FACTOR,
    INITIAL_BACKOFF_SECONDS,
    MAX_BACKOFF_SECONDS,
)
from polymarket_insider_tracker.ingestor.trade_rows import TradeObservation
from tests.fakes import FakeClock, FakeTradesServer, make_test_settings, trade_row
from tests.ingestor._poller_harness import RecordingTradeCallback, build_poller, seed_history

T0 = 1_788_983_720


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(float(T0))


@pytest.fixture
def server(clock: FakeClock) -> FakeTradesServer:
    return FakeTradesServer(clock=clock)


@pytest.fixture
def settings() -> PolymarketSettings:
    return make_test_settings(trades_url="https://trades.invalid/trades").polymarket


class FlakyArchive:
    def __init__(self, failures_before_success: int) -> None:
        self.failures_before_success = failures_before_success
        self.attempts = 0

    async def __call__(self, observation: TradeObservation) -> bool:
        del observation
        self.attempts += 1
        return self.attempts > self.failures_before_success


async def test_checkpoint_stalls_until_archive_succeeds(
    server: FakeTradesServer,
    clock: FakeClock,
    fake_redis: FakeAsyncRedis,
    settings: PolymarketSettings,
) -> None:
    seed_history(server, count=3, newest=T0 - 1)
    callback = RecordingTradeCallback()
    archive = FlakyArchive(failures_before_success=2)
    poller = build_poller(server, clock, fake_redis, settings, callback, archive_write=archive)
    await poller.run_cycle()
    anchored = poller.boundary.checkpoint
    assert anchored is not None
    clock.advance(5)
    server.publish(trade_row(timestamp=T0 + 5, transaction=15, wallet=5))
    start = clock()
    await poller.run_cycle()
    elapsed = clock() - start
    assert archive.attempts == 3
    assert callback.timestamps() == [T0 + 5]
    assert poller.boundary.checkpoint is not None
    assert poller.boundary.checkpoint.boundary_time == T0 + 5
    expected_min = INITIAL_BACKOFF_SECONDS + min(
        INITIAL_BACKOFF_SECONDS * BACKOFF_FACTOR, MAX_BACKOFF_SECONDS
    )
    assert elapsed >= expected_min
