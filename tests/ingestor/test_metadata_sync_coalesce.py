"""Hot-path CLOB miss coalesce and miss backoff."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fakeredis import FakeAsyncRedis

from polymarket_insider_tracker.ingestor.clob_client import ClobClient, ClobClientError
from polymarket_insider_tracker.ingestor.metadata_sync import MarketMetadataSync
from polymarket_insider_tracker.ingestor.models import Market, Token
from tests.fakes import FakeGammaClient


class CountingClob(ClobClient):
    def __init__(self, market: Market, *, delay: float = 0.05) -> None:
        super().__init__()
        self._market = market
        self._delay = delay
        self.calls = 0
        self.max_retries_seen: list[int | None] = []

    def get_market(self, condition_id: str, *, max_retries: int | None = None) -> Market:
        self.calls += 1
        self.max_retries_seen.append(max_retries)
        if condition_id != self._market.condition_id:
            raise ClobClientError(f"Failed to fetch market {condition_id}: not found")
        # Sync sleep in worker thread; coalesce must not start a second call.
        time.sleep(self._delay)
        return self._market


class FailingClob(ClobClient):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def get_market(self, condition_id: str, *, max_retries: int | None = None) -> Market:
        _ = max_retries
        self.calls += 1
        raise ClobClientError(f"Failed to fetch market {condition_id}: not found")


def _market() -> Market:
    return Market(
        condition_id="cond-coalesce",
        question="q",
        description="",
        tokens=(Token(token_id="t", outcome="Yes", price=Decimal("0.5")),),
        end_date=datetime(2026, 12, 31, tzinfo=UTC),
        active=True,
        closed=False,
    )


@pytest.mark.asyncio
async def test_concurrent_misses_share_one_clob_fetch() -> None:
    redis = FakeAsyncRedis()
    clob = CountingClob(_market())
    sync = MarketMetadataSync(redis=redis, clob_client=clob, gamma_client=FakeGammaClient())
    first, second = await asyncio.gather(
        sync.get_market("cond-coalesce"),
        sync.get_market("cond-coalesce"),
    )
    assert first is not None and second is not None
    assert first.condition_id == second.condition_id
    assert clob.calls == 1
    assert clob.max_retries_seen == [0]
    await redis.aclose()


@pytest.mark.asyncio
async def test_failed_miss_backs_off_without_refetch() -> None:
    redis = FakeAsyncRedis()
    clob = FailingClob()
    sync = MarketMetadataSync(redis=redis, clob_client=clob, gamma_client=FakeGammaClient())
    assert await sync.get_market("missing") is None
    assert await sync.get_market("missing") is None
    assert clob.calls == 1
    await redis.aclose()
