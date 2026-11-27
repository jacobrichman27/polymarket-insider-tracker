"""Backfill exclusions: no_private_edge and left-hot."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from polymarket_insider_tracker.config import ArchiveSettings
from polymarket_insider_tracker.ingestor.archive.featuring import enqueue_hot_backfill_for_market
from polymarket_insider_tracker.storage.models import Base, TradeModel


async def _session_with_trade(
    *, trade_ts: datetime, notional: str
) -> tuple[AsyncSession, AsyncEngine]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    session = factory()
    session.add(
        TradeModel(
            trade_ts=trade_ts,
            observation_id="obs-1",
            observed_at=trade_ts,
            archive_start_at=trade_ts,
            source_id="src",
            transaction_hash="0xtx",
            proxy_wallet="0xabc",
            condition_id="cond-1",
            token_id="tok",
            outcome=None,
            outcome_index=None,
            side="BUY",
            price=Decimal("0.5"),
            size_shares=Decimal(notional) * 2,
            notional_usdc=Decimal(notional),
            source="test",
            neg_risk=None,
            outcome_repair_status="not_needed",
            outcome_repaired=None,
            outcome_index_repaired=None,
            receipt_status="not_attempted",
            info_knowability_regime="unknown",
            knowability_label_source="unknown",
            raw_row_json=None,
        )
    )
    await session.commit()
    return session, engine


@pytest.mark.asyncio
async def test_no_private_edge_upgrade_enqueues_zero() -> None:
    now = datetime(2026, 11, 25, tzinfo=UTC)
    session, engine = await _session_with_trade(trade_ts=now - timedelta(days=1), notional="9000")
    archive = ArchiveSettings(ARCHIVE_ENABLED=True, ARCHIVE_FEATURING_ENABLED=True)
    try:
        count = await enqueue_hot_backfill_for_market(
            session,
            condition_id="cond-1",
            new_regime="no_private_edge",
            archive=archive,
            now=now,
        )
        assert count == 0
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_left_hot_fill_not_enqueued() -> None:
    now = datetime(2026, 11, 25, tzinfo=UTC)
    old = now - timedelta(days=20)
    session, engine = await _session_with_trade(trade_ts=old, notional="9000")
    archive = ArchiveSettings(
        ARCHIVE_ENABLED=True,
        ARCHIVE_FEATURING_ENABLED=True,
        ARCHIVE_HOT_WINDOW_DAYS=14,
    )
    try:
        count = await enqueue_hot_backfill_for_market(
            session,
            condition_id="cond-1",
            new_regime="private_edge_possible",
            archive=archive,
            now=now,
        )
        assert count == 0
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_hot_eligible_fill_enqueued_on_private_edge() -> None:
    now = datetime(2026, 11, 25, tzinfo=UTC)
    session, engine = await _session_with_trade(trade_ts=now - timedelta(days=1), notional="9000")
    archive = ArchiveSettings(ARCHIVE_ENABLED=True, ARCHIVE_FEATURING_ENABLED=True)
    try:
        count = await enqueue_hot_backfill_for_market(
            session,
            condition_id="cond-1",
            new_regime="private_edge_possible",
            archive=archive,
            now=now,
        )
        assert count == 1
    finally:
        await session.close()
        await engine.dispose()
