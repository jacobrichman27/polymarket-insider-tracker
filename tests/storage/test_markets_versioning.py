"""Append-on-change markets + snapshot join (US3)."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from polymarket_insider_tracker.ingestor.archive.markets import append_market_version, snapshot_at
from polymarket_insider_tracker.storage.models import Base


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as sess:
        yield sess
    await engine.dispose()


@pytest.mark.asyncio
async def test_append_on_change_and_snapshot_join(session: AsyncSession) -> None:
    t0 = datetime(2026, 11, 20, tzinfo=UTC)
    t1 = t0 + timedelta(hours=1)
    t2 = t0 + timedelta(hours=2)
    first = await append_market_version(
        session,
        condition_id="cond-1",
        token_outcomes={"tok-a": {"outcome": "Yes", "outcome_index": 0}},
        known_at=t0,
        question="Q1",
    )
    assert first is not None
    same = await append_market_version(
        session,
        condition_id="cond-1",
        token_outcomes={"tok-a": {"outcome": "Yes", "outcome_index": 0}},
        known_at=t1,
        question="Q1",
    )
    assert same is not None
    # SQLite may drop tzinfo on round-trip; compare UTC-normalized instants.
    assert same.known_at.replace(tzinfo=UTC) == t0
    second = await append_market_version(
        session,
        condition_id="cond-1",
        token_outcomes={
            "tok-a": {"outcome": "Yes", "outcome_index": 0},
            "tok-b": {"outcome": "No", "outcome_index": 1},
        },
        known_at=t1,
        question="Q1",
    )
    assert second is not None
    assert second.known_at == t1
    early = await snapshot_at(session, condition_id="cond-1", at=t0 + timedelta(minutes=30))
    late = await snapshot_at(session, condition_id="cond-1", at=t2)
    assert early is not None and "tok-b" not in early.token_outcomes
    assert late is not None and "tok-b" in late.token_outcomes
