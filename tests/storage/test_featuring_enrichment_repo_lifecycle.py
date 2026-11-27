"""Cover featuring work-item claim/complete and arm-status edges."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from polymarket_insider_tracker.storage.models import Base, TradeModel
from polymarket_insider_tracker.storage.repos import FeaturingEnrichmentRepository


def _trade(trade_ts: datetime, observation_id: str = "obs-life") -> TradeModel:
    return TradeModel(
        trade_ts=trade_ts,
        observation_id=observation_id,
        observed_at=trade_ts,
        archive_start_at=trade_ts,
        source_id="src",
        transaction_hash="0x",
        proxy_wallet="0xabc",
        condition_id="c",
        token_id="t",
        outcome=None,
        outcome_index=None,
        side="BUY",
        price=Decimal("1"),
        size_shares=Decimal("1"),
        notional_usdc=Decimal("1"),
        source="test",
        neg_risk=None,
        outcome_repair_status="not_needed",
        outcome_repaired=None,
        outcome_index_repaired=None,
        receipt_status="not_attempted",
        info_knowability_regime=None,
        knowability_label_source=None,
        raw_row_json=None,
    )


async def _memory() -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


@pytest.mark.asyncio
async def test_claim_empty_then_enqueue_dedupe() -> None:
    engine, factory = await _memory()
    now = datetime.now(UTC)
    async with factory() as session:
        repo = FeaturingEnrichmentRepository(session)
        assert await repo.claim_next_pending(now=now) is None
        first = await repo.enqueue_work(
            observation_id="obs-life",
            trade_ts=now,
            enrichment_budget_version="b.v1",
            trigger="insert_time",
            enqueued_at=now,
        )
        assert first is not None
        dup = await repo.enqueue_work(
            observation_id="obs-life",
            trade_ts=now,
            enrichment_budget_version="b.v1",
            trigger="insert_time",
            enqueued_at=now,
        )
        assert dup is None
    await engine.dispose()


@pytest.mark.asyncio
async def test_enqueue_rematerialize_uses_retry_trigger() -> None:
    engine, factory = await _memory()
    now = datetime.now(UTC)
    async with factory() as session:
        repo = FeaturingEnrichmentRepository(session)
        first = await repo.enqueue_work(
            observation_id="obs-life",
            trade_ts=now,
            enrichment_budget_version="b.v1",
            trigger="insert_time",
            enqueued_at=now,
        )
        assert first is not None
        remat = await repo.enqueue_rematerialize(
            observation_id="obs-life",
            trade_ts=now,
            enrichment_budget_version="b.v1",
            enqueued_at=now,
        )
        assert remat is not None
        assert remat.trigger == "retry"
        again = await repo.enqueue_rematerialize(
            observation_id="obs-life",
            trade_ts=now,
            enrichment_budget_version="b.v1",
            enqueued_at=now,
        )
        assert again is None
    await engine.dispose()


@pytest.mark.asyncio
async def test_claim_prefers_insert_time_over_older_regime_upgrade() -> None:
    engine, factory = await _memory()
    older = datetime(2026, 11, 20, 12, 0, 0, tzinfo=UTC)
    newer = datetime(2026, 11, 25, 12, 0, 0, tzinfo=UTC)
    async with factory() as session:
        session.add(_trade(older, "obs-upgrade"))
        session.add(_trade(newer, "obs-live"))
        await session.commit()
        repo = FeaturingEnrichmentRepository(session)
        await repo.enqueue_work(
            observation_id="obs-upgrade",
            trade_ts=older,
            enrichment_budget_version="b.v1",
            trigger="regime_upgrade",
            enqueued_at=older,
        )
        await repo.enqueue_work(
            observation_id="obs-live",
            trade_ts=newer,
            enrichment_budget_version="b.v1",
            trigger="insert_time",
            enqueued_at=newer,
        )
        claimed = await repo.claim_next_pending(now=newer)
        assert claimed is not None
        assert claimed.observation_id == "obs-live"
        assert claimed.trigger == "insert_time"
    await engine.dispose()


@pytest.mark.asyncio
async def test_claim_complete_and_missing_work() -> None:
    engine, factory = await _memory()
    now = datetime.now(UTC)
    async with factory() as session:
        repo = FeaturingEnrichmentRepository(session)
        await repo.enqueue_work(
            observation_id="obs-life",
            trade_ts=now,
            enrichment_budget_version="b.v1",
            trigger="insert_time",
            enqueued_at=now,
        )
        claimed = await repo.claim_next_pending(now=now)
        assert claimed is not None
        await repo.complete_work(claimed.work_id, finished_at=now)
        await session.commit()
        assert claimed.status == "completed"
        assert await repo.claim_next_pending(now=now) is None
        await repo.complete_work(9_999_999, finished_at=now)
    await engine.dispose()


@pytest.mark.asyncio
async def test_arm_status_missing_and_partial() -> None:
    engine, factory = await _memory()
    now = datetime.now(UTC)
    async with factory() as session:
        session.add(_trade(now))
        await session.commit()
        repo = FeaturingEnrichmentRepository(session)
        await repo.update_arm_statuses(observation_id="missing", trade_ts=now, gamma_status="ok")
        await repo.update_arm_statuses(
            observation_id="obs-life", trade_ts=now, receipt_status="pending"
        )
        await repo.update_arm_statuses(observation_id="obs-life", trade_ts=now, gamma_status="ok")
        await session.commit()
        trade = await session.get(TradeModel, {"trade_ts": now, "observation_id": "obs-life"})
        assert trade is not None
        assert trade.receipt_status == "pending"
        assert trade.gamma_enrichment_status == "ok"
    await engine.dispose()
