"""Archive-enabled TradePoller fan-out isolation matrix."""

from __future__ import annotations

import pytest
from fakeredis import FakeAsyncRedis

from polymarket_insider_tracker.config import PolymarketSettings
from polymarket_insider_tracker.ingestor.models import TradeEvent
from polymarket_insider_tracker.ingestor.trade_poller import TradePoller
from polymarket_insider_tracker.ingestor.trade_rows import TradeObservation
from tests.fakes import FakeClock, FakeTradesServer, make_test_settings, trade_row
from tests.fakes.trades import synthetic_wallet
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


class RecordingArchive:
    def __init__(self, *, succeed: bool = True) -> None:
        self.observations: list[TradeObservation] = []
        self.succeed = succeed

    async def __call__(self, observation: TradeObservation) -> bool:
        self.observations.append(observation)
        return self.succeed


class FailingMonitor(RecordingTradeCallback):
    async def __call__(self, trade: TradeEvent) -> None:
        self.trades.append(trade)
        raise RuntimeError("monitor boom")


async def test_archive_happy_path_credits_after_insert(
    server: FakeTradesServer,
    clock: FakeClock,
    fake_redis: FakeAsyncRedis,
    settings: PolymarketSettings,
) -> None:
    seed_history(server, count=3, newest=T0 - 1)
    callback = RecordingTradeCallback()
    archive = RecordingArchive()
    poller = build_poller(server, clock, fake_redis, settings, callback, archive_write=archive)
    await poller.run_cycle()
    clock.advance(5)
    server.publish(trade_row(timestamp=T0 + 1, transaction=11, wallet=1))
    await poller.run_cycle()
    assert len(archive.observations) == 1
    assert archive.observations[0].raw_row is not None
    assert callback.timestamps() == [T0 + 1]
    assert archive.observations[0].identity in poller.boundary.window


async def test_archive_fail_still_invokes_monitor_without_retain(
    server: FakeTradesServer,
    clock: FakeClock,
    fake_redis: FakeAsyncRedis,
    settings: PolymarketSettings,
) -> None:
    seed_history(server, count=3, newest=T0 - 1)
    callback = RecordingTradeCallback()
    archive = RecordingArchive(succeed=False)
    holder: list[TradePoller] = []

    async def sleeper(delay: float) -> None:
        await holder[0].stop()
        await clock.sleep(delay)

    poller = build_poller(
        server,
        clock,
        fake_redis,
        settings,
        callback,
        archive_write=archive,
        sleeper=sleeper,
    )
    holder.append(poller)
    await poller.run_cycle()
    clock.advance(5)
    server.publish(trade_row(timestamp=T0 + 2, transaction=12, wallet=2))
    await poller.run_cycle()
    assert len(callback.trades) == 1
    assert callback.trades[0].wallet_address == synthetic_wallet(2)
    assert all(obs.identity not in poller.boundary.window for obs in archive.observations)
    assert poller.boundary.checkpoint is not None
    assert poller.boundary.checkpoint.boundary_time == T0 - 1


async def test_monitor_fail_after_archive_ok_still_retains(
    server: FakeTradesServer,
    clock: FakeClock,
    fake_redis: FakeAsyncRedis,
    settings: PolymarketSettings,
) -> None:
    seed_history(server, count=3, newest=T0 - 1)
    callback = FailingMonitor()
    archive = RecordingArchive()
    poller = build_poller(server, clock, fake_redis, settings, callback, archive_write=archive)
    await poller.run_cycle()
    clock.advance(5)
    server.publish(trade_row(timestamp=T0 + 3, transaction=13, wallet=3))
    await poller.run_cycle()
    assert len(archive.observations) == 1
    assert archive.observations[0].identity in poller.boundary.window


async def test_monitor_only_default_retains_after_monitor(
    server: FakeTradesServer,
    clock: FakeClock,
    fake_redis: FakeAsyncRedis,
    settings: PolymarketSettings,
) -> None:
    seed_history(server, count=3, newest=T0 - 1)
    callback = RecordingTradeCallback()
    poller = build_poller(server, clock, fake_redis, settings, callback)
    await poller.run_cycle()
    clock.advance(5)
    server.publish(trade_row(timestamp=T0 + 4, transaction=14, wallet=4))
    await poller.run_cycle()
    assert callback.timestamps() == [T0 + 4]
    assert len(poller.boundary.window) >= 1
