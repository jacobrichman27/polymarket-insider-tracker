"""Market-grain warm + process-scoped Decisions budget (never per fill)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from polymarket_insider_tracker.config import ArchiveSettings
from polymarket_insider_tracker.ingestor.archive import workers as workers_mod
from polymarket_insider_tracker.ingestor.archive.decisions_client import (
    BudgetGate,
    HttpxDecisionsClient,
)
from polymarket_insider_tracker.ingestor.archive.workers import (
    MarketWarmCoordinator,
    build_warm_coordinator,
    schedule_market_warm,
    warm_market_metadata,
)
from polymarket_insider_tracker.storage.models import Base, MarketVersionModel
from tests.test_config import env_context


class _SessionDb:
    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory

    @asynccontextmanager
    async def get_async_session(self) -> AsyncGenerator[AsyncSession, None]:
        async with self._factory() as session:
            yield session


def _archive(**extra: str) -> ArchiveSettings:
    env = {
        "DATABASE_URL": "postgresql+psycopg://user:pass@localhost/db",
        "ARCHIVE_ENABLED": "true",
        "ARCHIVE_KNOWABILITY_MODEL_ENABLED": "false",
        **extra,
    }
    with env_context(env, clear=True):
        return ArchiveSettings()


def _gamma(condition_id: str) -> dict[str, object]:
    return {
        "conditionId": condition_id,
        "question": f"Question for {condition_id}?",
        "outcomes": '["Yes", "No"]',
        "clobTokenIds": '["t0", "t1"]',
    }


async def _memory_db() -> tuple[AsyncEngine, _SessionDb, async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, _SessionDb(factory), factory


@pytest.mark.asyncio
async def test_second_warm_skips_gamma_fetch_when_market_exists() -> None:
    engine, db, factory = await _memory_db()
    archive = _archive()
    fetches = 0

    async def fetch(condition_id: str) -> dict[str, object]:
        nonlocal fetches
        fetches += 1
        return _gamma(condition_id)

    coord = build_warm_coordinator(archive)
    assert await warm_market_metadata(
        db, condition_id="c1", archive=archive, coordinator=coord, fetch_market=fetch
    )
    assert await warm_market_metadata(
        db, condition_id="c1", archive=archive, coordinator=coord, fetch_market=fetch
    )
    assert fetches == 1
    async with factory() as session:
        rows = list((await session.execute(select(MarketVersionModel))).scalars().all())
    assert len(rows) == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_schedule_dedupes_in_flight_same_condition() -> None:
    engine, db, _factory = await _memory_db()
    archive = _archive()
    started = asyncio.Event()
    release = asyncio.Event()
    fetches = 0
    coord = build_warm_coordinator(archive)

    async def slow_fetch(condition_id: str) -> dict[str, object]:
        nonlocal fetches
        fetches += 1
        started.set()
        await release.wait()
        return _gamma(condition_id)

    loop = asyncio.get_running_loop()
    schedule_market_warm(
        loop, db, condition_id="c1", archive=archive, coordinator=coord, fetch_market=slow_fetch
    )
    schedule_market_warm(
        loop, db, condition_id="c1", archive=archive, coordinator=coord, fetch_market=slow_fetch
    )
    await asyncio.wait_for(started.wait(), timeout=1.0)
    release.set()
    await asyncio.sleep(0.05)
    assert fetches == 1
    await engine.dispose()


def test_shared_budget_gate_accumulates_across_clients() -> None:
    gate = BudgetGate(max_calls_per_day=1)
    coord = MarketWarmCoordinator(budget=gate)
    assert coord.budget.allow("2026-11-25") is True
    coord.budget.record_success()
    assert coord.budget.allow("2026-11-25") is False


@pytest.mark.asyncio
async def test_shared_coordinator_budget_blocks_second_model_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine, db, factory = await _memory_db()
    archive = _archive(
        ARCHIVE_KNOWABILITY_MODEL_ENABLED="true",
        ARCHIVE_KNOWABILITY_MODEL_API_KEY="sk-test",
        ARCHIVE_KNOWABILITY_MODEL_MAX_CALLS_PER_DAY="1",
    )
    posts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal posts
        del request
        posts += 1
        return httpx.Response(
            200,
            json={
                "model": "gpt-6-luna",
                "answers": [
                    {
                        "type": "choice",
                        "name": "knowability_regime",
                        "choice": "private_edge_possible",
                    }
                ],
            },
        )

    transport = httpx.MockTransport(handler)

    def client_for(
        archive_settings: ArchiveSettings, *, budget: BudgetGate
    ) -> HttpxDecisionsClient:
        key = archive_settings.knowability_model_api_key
        assert key is not None
        return HttpxDecisionsClient(
            api_key=key.get_secret_value(),
            budget=budget,
            transport=transport,
        )

    monkeypatch.setattr(workers_mod, "_decisions_client", client_for)
    coord = build_warm_coordinator(archive)

    async def fetch_a(_cid: str) -> dict[str, object]:
        return _gamma("a")

    async def fetch_b(_cid: str) -> dict[str, object]:
        return _gamma("b")

    await warm_market_metadata(
        db, condition_id="a", archive=archive, coordinator=coord, fetch_market=fetch_a
    )
    await warm_market_metadata(
        db, condition_id="b", archive=archive, coordinator=coord, fetch_market=fetch_b
    )
    assert posts == 1
    async with factory() as session:
        rows = list((await session.execute(select(MarketVersionModel))).scalars().all())
    assert len(rows) == 2
    await engine.dispose()
