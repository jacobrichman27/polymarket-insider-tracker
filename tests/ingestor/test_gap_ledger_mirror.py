"""Redis ingest loss → durable ingest_gap_events mirror."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from polymarket_insider_tracker.ingestor.archive import gap_ledger
from polymarket_insider_tracker.ingestor.observation_boundary import LossEvent, LossReason
from polymarket_insider_tracker.storage.models import Base, IngestGapEventModel

SOURCE = "polymarket:data-api.trades"


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
async def test_mirror_loss_event_persists_ingest_loss(session: AsyncSession) -> None:
    event = LossEvent(
        from_time=100,
        to_time=200,
        reason=LossReason.HORIZON_EXPIRED,
        detected_at=210,
        recorded_at=211,
        pages_examined=3,
    )
    await gap_ledger.mirror_loss_event(session, source_id=SOURCE, event=event)
    await session.commit()
    row = (await session.execute(select(IngestGapEventModel))).scalar_one()
    assert row.class_ == "ingest_loss"
    assert row.reason == LossReason.HORIZON_EXPIRED.value
    assert row.pages_examined == 3
    assert row.redis_payload is not None
