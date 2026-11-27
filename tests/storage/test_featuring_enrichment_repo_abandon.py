"""Exercise abandon_work repository path."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from polymarket_insider_tracker.storage.models import Base, EnrichmentWorkItemModel
from polymarket_insider_tracker.storage.repos import FeaturingEnrichmentRepository


@pytest.mark.asyncio
async def test_abandon_work_sets_terminal_status() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    async with factory() as session:
        work = EnrichmentWorkItemModel(
            observation_id="obs",
            trade_ts=now,
            enrichment_budget_version="b.v1",
            trigger="insert_time",
            status="running",
            enqueued_at=now,
            started_at=now,
        )
        session.add(work)
        await session.commit()
        repo = FeaturingEnrichmentRepository(session)
        await repo.abandon_work(work.work_id, finished_at=now, last_error="budget")
        await session.commit()
        assert work.status == "abandoned"
        assert work.last_error == "budget"
    await engine.dispose()
