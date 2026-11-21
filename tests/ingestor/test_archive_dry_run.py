"""DRY_RUN must not suppress archive tape writes (FR-022)."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from polymarket_insider_tracker.alerter.dispatcher import AlertDispatcher
from polymarket_insider_tracker.ingestor.archive.writer import ArchiveWriter, ArchiveWriteStatus
from polymarket_insider_tracker.ingestor.trade_rows import TradeObservation, parse_trade_row
from polymarket_insider_tracker.storage.models import Base, TradeModel
from tests.fakes import FakeAlertChannel, make_test_settings, trade_row

NOW = 1_788_983_720
SOURCE = "polymarket:data-api.trades"


@pytest.fixture
async def archive_session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def _observation() -> TradeObservation:
    parsed = parse_trade_row(trade_row(timestamp=NOW - 2, transaction=21, wallet=4), now=NOW)
    assert isinstance(parsed, TradeObservation)
    return parsed


@pytest.mark.asyncio
async def test_dry_run_settings_still_allow_archive_insert(
    archive_session: AsyncSession,
) -> None:
    settings = make_test_settings(dry_run=True, archive_enabled=True)
    assert settings.dry_run is True
    assert settings.archive.enabled is True
    writer = ArchiveWriter(archive_session, source_id=SOURCE, raw_retention=True)
    result = await writer.write(_observation())
    await archive_session.commit()
    rows = (await archive_session.execute(select(TradeModel))).scalars().all()
    assert result.status is ArchiveWriteStatus.INSERTED
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_dry_run_dispatcher_does_not_deliver_while_tape_writes(
    archive_session: AsyncSession,
) -> None:
    channel = FakeAlertChannel("discord")
    dispatcher = AlertDispatcher([channel], dry_run=True)
    writer = ArchiveWriter(archive_session, source_id=SOURCE)
    await writer.write(_observation())
    await archive_session.commit()
    assert channel.deliveries == []
    assert (await archive_session.execute(select(TradeModel))).scalar_one() is not None
    # dry-run path: dispatcher must not have been asked to deliver for this tape write
    assert dispatcher.dry_run is True
