"""Archive insert path must not await slow Gamma repair (US1/US5)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from polymarket_insider_tracker.config import ArchiveSettings
from polymarket_insider_tracker.ingestor.archive.workers import (
    build_warm_coordinator,
    schedule_market_warm,
)
from polymarket_insider_tracker.storage.models import Base
from tests.test_config import env_context


class _SessionDb:
    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory

    @asynccontextmanager
    async def get_async_session(self) -> AsyncGenerator[AsyncSession, None]:
        async with self._factory() as session:
            yield session


@pytest.mark.asyncio
async def test_schedule_market_warm_does_not_block_caller() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    db = _SessionDb(factory)
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow_fetch(_condition_id: str) -> dict[str, object] | None:
        started.set()
        await release.wait()
        return None

    with env_context(
        {
            "DATABASE_URL": "postgresql+psycopg://user:pass@localhost/db",
            "ARCHIVE_ENABLED": "true",
        },
        clear=True,
    ):
        archive = ArchiveSettings()

    schedule_market_warm(
        asyncio.get_running_loop(),
        db,
        condition_id="c1",
        archive=archive,
        coordinator=build_warm_coordinator(archive),
        fetch_market=slow_fetch,
    )
    await asyncio.wait_for(started.wait(), timeout=1.0)
    release.set()
    await asyncio.sleep(0)
    await engine.dispose()
