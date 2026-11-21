"""Abandon owed archive writes when fills age past the emission floor."""

from __future__ import annotations

from fakeredis import FakeAsyncRedis

from polymarket_insider_tracker.ingestor.trade_poller import TradePoller
from polymarket_insider_tracker.ingestor.trade_rows import TradeObservation
from tests.fakes import FakeClock, FakeTradesServer, make_test_settings, trade_row
from tests.ingestor._poller_harness import RecordingTradeCallback, build_poller, seed_history

T0 = 1_788_983_720


class RecordingAbandon:
    def __init__(self) -> None:
        self.abandoned: list[str] = []

    async def __call__(self, observation: TradeObservation) -> None:
        self.abandoned.append(observation.identity)


class FailStaleArchive:
    """Fail inserts for rows older than ``cutoff``; succeed for newer ones."""

    def __init__(self, cutoff: int) -> None:
        self.cutoff = cutoff

    async def __call__(self, observation: TradeObservation) -> bool:
        return observation.provider_timestamp >= self.cutoff


async def test_loss_mirror_receives_restart_beyond_horizon_event(
    fake_redis: FakeAsyncRedis,
) -> None:
    clock = FakeClock(float(T0))
    server = FakeTradesServer(clock=clock)
    settings = make_test_settings(trades_url="https://trades.invalid/trades").polymarket
    mirrored: list[object] = []

    async def mirror(event: object) -> None:
        mirrored.append(event)

    seed_history(server, count=3, newest=T0 - 1)
    first = build_poller(server, clock, fake_redis, settings, RecordingTradeCallback())
    await first.run_cycle()
    await first.stop()
    clock.advance(700)
    for offset in range(3):
        server.publish(trade_row(timestamp=T0 + 650 + offset, transaction=50 + offset, wallet=50))
    second = build_poller(
        server,
        clock,
        fake_redis,
        settings,
        RecordingTradeCallback(),
        loss_mirror=mirror,
    )
    await second.run_cycle()
    assert len(mirrored) == 1


async def test_abandon_without_callback_still_clears_owed(fake_redis: FakeAsyncRedis) -> None:
    clock = FakeClock(float(T0))
    server = FakeTradesServer(clock=clock)
    settings = make_test_settings(trades_url="https://trades.invalid/trades").polymarket
    holder: list[TradePoller] = []

    async def sleeper(delay: float) -> None:
        await holder[0].stop()
        await clock.sleep(delay)

    poller = build_poller(
        server,
        clock,
        fake_redis,
        settings,
        RecordingTradeCallback(),
        archive_write=FailStaleArchive(cutoff=T0 + 100),
        sleeper=sleeper,
    )
    holder.append(poller)
    seed_history(server, count=3, newest=T0 - 1)
    await poller.run_cycle()
    clock.advance(5)
    server.publish(trade_row(timestamp=T0 + 1, transaction=42, wallet=42))
    await poller.run_cycle()
    clock.advance(700)
    server.publish(trade_row(timestamp=T0 + 700, transaction=43, wallet=43))
    await poller.run_cycle()


async def test_abandon_unreachable_calls_callback_when_floor_passes(
    fake_redis: FakeAsyncRedis,
) -> None:
    clock = FakeClock(float(T0))
    server = FakeTradesServer(clock=clock)
    settings = make_test_settings(trades_url="https://trades.invalid/trades").polymarket
    abandon = RecordingAbandon()
    holder: list[TradePoller] = []

    async def sleeper(delay: float) -> None:
        await holder[0].stop()
        await clock.sleep(delay)

    archive = FailStaleArchive(cutoff=T0 + 100)
    poller = build_poller(
        server,
        clock,
        fake_redis,
        settings,
        RecordingTradeCallback(),
        archive_write=archive,
        abandon_write=abandon,
        sleeper=sleeper,
    )
    holder.append(poller)
    seed_history(server, count=3, newest=T0 - 1)
    await poller.run_cycle()
    clock.advance(5)
    server.publish(trade_row(timestamp=T0 + 1, transaction=40, wallet=40))
    await poller.run_cycle()
    assert abandon.abandoned == []

    clock.advance(700)
    server.publish(trade_row(timestamp=T0 + 700, transaction=41, wallet=41))
    await poller.run_cycle()
    assert len(abandon.abandoned) == 1
