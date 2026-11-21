"""Shared poller test harness: the downstream consumer and the poller-wiring recipe.

Not collected as tests (its name does not start with ``test_``). The v1 and v2 poller
suites share this single home for the consumer double that records deliveries and for
building a ``TradePoller`` over a fake provider on the loopback clock.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol

import httpx
from fakeredis import FakeAsyncRedis, FakeServer

from polymarket_insider_tracker.config import PolymarketSettings
from polymarket_insider_tracker.ingestor.models import TradeEvent
from polymarket_insider_tracker.ingestor.observation_boundary import LossEvent
from polymarket_insider_tracker.ingestor.trade_poller import TradePoller
from polymarket_insider_tracker.ingestor.trade_rows import TradeObservation
from tests.fakes import FakeClock, FakeTradesServer, trade_row

ArchiveWriteFn = Callable[[TradeObservation], Awaitable[bool]]
AbandonFn = Callable[[TradeObservation], Awaitable[None]]
LossMirrorFn = Callable[[LossEvent], Awaitable[None]]
Sleeper = Callable[[float], Awaitable[None]]

DEFAULT_HISTORY_NEWEST = 1_788_983_719


class RecordingTradeCallback:
    """The downstream trade consumer; keeps every delivered event in order."""

    def __init__(self) -> None:
        self.trades: list[TradeEvent] = []

    async def __call__(self, trade: TradeEvent) -> None:
        self.trades.append(trade)

    def timestamps(self) -> list[int]:
        return [int(trade.timestamp.timestamp()) for trade in self.trades]


class TradeProvider(Protocol):
    """A fake provider exposing an ``httpx`` client to its scripted responses."""

    def client(self) -> httpx.AsyncClient: ...


def seed_history(
    server: FakeTradesServer, *, count: int = 5, newest: int = DEFAULT_HISTORY_NEWEST
) -> None:
    """Publish ``count`` historical rows ending at ``newest`` (oldest first offsets)."""
    for offset in range(count):
        server.publish(trade_row(timestamp=newest - offset * 60, transaction=offset, wallet=offset))


def build_poller(
    server: TradeProvider,
    clock: FakeClock,
    redis: FakeAsyncRedis,
    settings: PolymarketSettings,
    callback: RecordingTradeCallback,
    *,
    archive_write: ArchiveWriteFn | None = None,
    abandon_write: AbandonFn | None = None,
    loss_mirror: LossMirrorFn | None = None,
    sleeper: Sleeper | None = None,
) -> TradePoller:
    """A poller over ``server`` on the fake clock; the shared wiring recipe."""
    return TradePoller(
        callback,
        redis=redis,
        settings=settings,
        http_client=server.client(),
        clock=clock,
        sleeper=clock.sleep if sleeper is None else sleeper,
        random_source=lambda: 0.0,
        archive_write=archive_write,
        abandon_write=abandon_write,
        loss_mirror=loss_mirror,
    )


class RedisDropsOnRequest:
    """A provider whose first served request cuts the Redis server, after the boundary loaded."""

    def __init__(self, server: FakeTradesServer, redis_server: FakeServer) -> None:
        self._server = server
        self._redis_server = redis_server
        self._dropped = False

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self._serve))

    def _serve(self, request: httpx.Request) -> httpx.Response:
        if not self._dropped:
            self._dropped = True
            self._redis_server.connected = False
        return self._server(request)
