"""Archive writer behavioral contracts beyond storage."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from polymarket_insider_tracker.ingestor.archive.writer import ArchiveWriter, ArchiveWriteStatus
from polymarket_insider_tracker.ingestor.trade_rows import TradeObservation, parse_trade_row
from polymarket_insider_tracker.storage.models import Base
from tests.fakes.trades import trade_row

NOW = 1_788_983_720
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


def _observation() -> TradeObservation:
    parsed = parse_trade_row(trade_row(timestamp=NOW - 3, transaction=9, wallet=1), now=NOW)
    assert isinstance(parsed, TradeObservation)
    return parsed


@pytest.mark.asyncio
async def test_archive_write_does_not_require_gamma(archive_session: AsyncSession) -> None:
    """Writer succeeds with no Gamma/knowability client in scope."""
    writer = ArchiveWriter(archive_session, source_id=SOURCE)
    result = await writer.write(_observation())
    assert result.status is ArchiveWriteStatus.INSERTED
    assert "gamma" not in ArchiveWriter.write.__code__.co_names
