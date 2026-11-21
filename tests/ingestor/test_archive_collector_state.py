"""Set-once archive_start_at collector state tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from polymarket_insider_tracker.ingestor.archive.state import (
    ArchiveStartOverwriteError,
    ensure_archive_start,
    refuse_silent_overwrite,
)
from polymarket_insider_tracker.storage.models import Base

SOURCE = "polymarket:data-api.trades"


@pytest.fixture
async def archive_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_archive_start_set_once(archive_session: AsyncSession) -> None:
    first_stamp = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
    first = await ensure_archive_start(
        archive_session, source_id=SOURCE, raw_retention=True, now=first_stamp
    )
    second = await ensure_archive_start(
        archive_session,
        source_id=SOURCE,
        raw_retention=False,
        now=first_stamp + timedelta(hours=5),
    )
    await archive_session.commit()

    def as_utc(value: datetime) -> datetime:
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    assert as_utc(first.archive_start_at) == first_stamp
    assert as_utc(second.archive_start_at) == first_stamp
    assert second.raw_retention is True


@pytest.mark.asyncio
async def test_refuse_silent_overwrite(archive_session: AsyncSession) -> None:
    stamp = datetime(2026, 11, 20, 15, 0, tzinfo=UTC)
    await ensure_archive_start(archive_session, source_id=SOURCE, raw_retention=True, now=stamp)
    with pytest.raises(ArchiveStartOverwriteError):
        await refuse_silent_overwrite(
            archive_session,
            source_id=SOURCE,
            proposed_start=stamp + timedelta(days=1),
        )
