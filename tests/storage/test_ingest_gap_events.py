"""Write-failure gap ledger lifecycle tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from polymarket_insider_tracker.ingestor.archive import gap_ledger
from polymarket_insider_tracker.storage.models import Base, IngestGapEventModel

SOURCE = "polymarket:data-api.trades"
OBS = "a" * 64


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with factory() as db:
        yield db
    await engine.dispose()


@pytest.mark.asyncio
async def test_write_failure_open_resolve(session: AsyncSession) -> None:
    await gap_ledger.record_write_failure(session, source_id=SOURCE, observation_id=OBS)
    await gap_ledger.resolve_write_failure(session, source_id=SOURCE, observation_id=OBS)
    await session.commit()
    row = (await session.execute(select(IngestGapEventModel))).scalar_one()
    assert row.class_ == "write_failure"
    assert row.status == "resolved"
    assert row.resolved_at is not None


@pytest.mark.asyncio
async def test_write_failure_abandon(session: AsyncSession) -> None:
    await gap_ledger.record_write_failure(session, source_id=SOURCE, observation_id=OBS)
    await gap_ledger.abandon_write_failure(session, source_id=SOURCE, observation_id=OBS)
    await session.commit()
    row = (await session.execute(select(IngestGapEventModel))).scalar_one()
    assert row.status == "abandoned"
    assert row.reason == "archive_insert_abandoned"
