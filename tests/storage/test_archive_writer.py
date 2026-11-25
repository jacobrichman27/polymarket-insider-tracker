"""Idempotent archive writer persistence tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from polymarket_insider_tracker.ingestor.archive.writer import ArchiveWriter, ArchiveWriteStatus
from polymarket_insider_tracker.ingestor.trade_rows import TradeObservation, parse_trade_row
from polymarket_insider_tracker.storage.models import Base, RiskAssessmentModel, TradeModel
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


def _observation(*, quiet: bool = False) -> TradeObservation:
    size = "1" if quiet else "5000"
    row = trade_row(timestamp=NOW - 5, transaction=42, wallet=7, price="0.55", size=size)
    parsed = parse_trade_row(row, now=NOW)
    assert isinstance(parsed, TradeObservation)
    return parsed


@pytest.mark.asyncio
async def test_idempotent_insert_keeps_single_row(archive_session: AsyncSession) -> None:
    writer = ArchiveWriter(archive_session, source_id=SOURCE, raw_retention=True)
    observation = _observation()
    first = await writer.write(observation)
    second = await writer.write(observation)
    await archive_session.commit()
    rows = (
        (
            await archive_session.execute(
                select(TradeModel).where(TradeModel.observation_id == observation.identity)
            )
        )
        .scalars()
        .all()
    )
    assert first.status is ArchiveWriteStatus.INSERTED
    assert second.status is ArchiveWriteStatus.DUPLICATE
    assert len(rows) == 1
    assert rows[0].raw_row_json is not None
    assert rows[0].info_knowability_regime == "unknown"
    assert rows[0].outcome_repair_status in {"not_attempted", "not_needed"}


@pytest.mark.asyncio
async def test_quiet_fill_persists_without_risk_assessment(archive_session: AsyncSession) -> None:
    writer = ArchiveWriter(archive_session, source_id=SOURCE, raw_retention=True)
    observation = _observation(quiet=True)
    result = await writer.write(observation)
    await archive_session.commit()
    assessments = (await archive_session.execute(select(RiskAssessmentModel))).scalars().all()
    trades = (await archive_session.execute(select(TradeModel))).scalars().all()
    assert result.status is ArchiveWriteStatus.INSERTED
    assert len(trades) == 1
    assert trades[0].size_shares == Decimal("1")
    assert assessments == []


@pytest.mark.asyncio
async def test_raw_off_stores_null_raw_column(archive_session: AsyncSession) -> None:
    writer = ArchiveWriter(archive_session, source_id=SOURCE, raw_retention=False)
    observation = _observation()
    await writer.write(observation)
    await archive_session.commit()
    row = (await archive_session.execute(select(TradeModel))).scalar_one()
    assert row.raw_row_json is None
