"""Markets writer runs with archive on even when repair is off (US3)."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from polymarket_insider_tracker.config import ArchiveSettings
from polymarket_insider_tracker.ingestor.archive.workers import warm_market_metadata
from polymarket_insider_tracker.storage.models import Base, MarketVersionModel
from tests.test_config import env_context


class _SessionDb:
    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory

    @asynccontextmanager
    async def get_async_session(self) -> AsyncGenerator[AsyncSession, None]:
        async with self._factory() as session:
            yield session


@pytest.mark.asyncio
async def test_markets_writer_with_archive_on_repair_off() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    db = _SessionDb(factory)

    with env_context(
        {
            "DATABASE_URL": "postgresql+psycopg://user:pass@localhost/db",
            "ARCHIVE_ENABLED": "true",
            "ARCHIVE_OUTCOME_REPAIR_ENABLED": "false",
        },
        clear=True,
    ):
        archive = ArchiveSettings()

    assert archive.enabled is True
    assert archive.outcome_repair_enabled is False

    async def fetch(_condition_id: str) -> dict[str, object]:
        # Documented Gamma market fields: outcomes / clobTokenIds as JSON strings.
        return {
            "conditionId": "c1",
            "question": "Will BTC be up or down on 2026-11-24?",
            "outcomes": '["Up", "Down"]',
            "clobTokenIds": '["t0", "t1"]',
        }

    await warm_market_metadata(db, condition_id="c1", archive=archive, fetch_market=fetch)
    async with factory() as session:
        rows = list((await session.execute(select(MarketVersionModel))).scalars().all())
    assert len(rows) == 1
    assert rows[0].condition_id == "c1"
    await engine.dispose()
