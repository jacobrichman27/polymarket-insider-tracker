"""Live repair KPI refresh from trades tape (SC-005)."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from polymarket_insider_tracker.config import ArchiveSettings
from polymarket_insider_tracker.ingestor.archive.repair_kpi import OutcomeRepairHealthSignals
from polymarket_insider_tracker.ingestor.archive.workers import refresh_repair_kpi
from polymarket_insider_tracker.storage.models import (
    ArchiveCollectorStateModel,
    Base,
    TradeModel,
)
from polymarket_insider_tracker.storage.repos import TradeArchiveRepository
from tests.test_config import env_context


class _SessionDb:
    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory

    @asynccontextmanager
    async def get_async_session(self) -> AsyncGenerator[AsyncSession, None]:
        async with self._factory() as session:
            yield session


def _archive() -> ArchiveSettings:
    with env_context(
        {
            "DATABASE_URL": "postgresql+psycopg://user:pass@localhost/db",
            "ARCHIVE_ENABLED": "true",
            "ARCHIVE_OUTCOME_REPAIR_ENABLED": "true",
            "ARCHIVE_OUTCOME_REPAIR_LAG_SECONDS": "300",
            "ARCHIVE_OUTCOME_REPAIR_UNREPAIRED_MAX_RATIO": "0.05",
        },
        clear=True,
    ):
        return ArchiveSettings()


def _trade(
    *,
    trade_ts: datetime,
    observation_id: str,
    outcome: str | None,
    outcome_index: int | None,
    status: str,
) -> TradeModel:
    return TradeModel(
        trade_ts=trade_ts,
        observation_id=observation_id,
        observed_at=trade_ts,
        archive_start_at=trade_ts,
        source_id="src",
        transaction_hash=f"0x{observation_id}",
        proxy_wallet="0xabc",
        condition_id="c1",
        token_id="tok",
        outcome=outcome,
        outcome_index=outcome_index,
        side="BUY",
        price=Decimal("0.5"),
        size_shares=Decimal("1"),
        notional_usdc=Decimal("0.5"),
        source="api",
        neg_risk=None,
        outcome_repair_status=status,
        outcome_repaired=None,
        outcome_index_repaired=None,
        receipt_status="unknown",
        info_knowability_regime=None,
        knowability_label_source=None,
        raw_row_json=None,
    )


@pytest.mark.asyncio
async def test_refresh_repair_kpi_marks_lag_breach() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    db = _SessionDb(factory)
    archive = _archive()
    health = OutcomeRepairHealthSignals()
    now = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)
    cutover = now - timedelta(hours=1)
    stale = now - timedelta(seconds=400)

    async with factory() as session:
        session.add(
            ArchiveCollectorStateModel(
                source_id="src",
                archive_start_at=cutover,
                raw_retention=True,
                repair_enabled_at=cutover,
                updated_at=now,
            )
        )
        session.add(
            _trade(
                trade_ts=stale,
                observation_id="thin-lag",
                outcome=None,
                outcome_index=999,
                status="not_attempted",
            )
        )
        session.add(
            _trade(
                trade_ts=cutover - timedelta(hours=2),
                observation_id="pre-cutover",
                outcome=None,
                outcome_index=999,
                status="not_attempted",
            )
        )
        session.add(
            _trade(
                trade_ts=stale,
                observation_id="usable",
                outcome="Yes",
                outcome_index=0,
                status="not_needed",
            )
        )
        await session.commit()

    await refresh_repair_kpi(db, source_id="src", archive=archive, health=health, now=now)
    snap = health.last_snapshot
    assert snap is not None
    assert snap.thin_post_cutover == 1
    assert snap.not_attempted_past_lag == 1
    assert snap.lag_breach is True
    assert health.evaluate().status == "degraded"
    await engine.dispose()


@pytest.mark.asyncio
async def test_count_unrepaired_ratio_population() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime(2026, 11, 25, 12, 0, tzinfo=UTC)
    cutover = now - timedelta(hours=2)
    async with factory() as session:
        for index, status in enumerate(("unrepaired", "ok", "not_attempted")):
            session.add(
                _trade(
                    trade_ts=cutover + timedelta(minutes=index),
                    observation_id=f"t{index}",
                    outcome="",
                    outcome_index=999,
                    status=status,
                )
            )
        await session.commit()
        counts = await TradeArchiveRepository(session).count_outcome_repair_kpi(
            cutover=cutover, now=now, lag_seconds=300
        )
    assert counts.thin_post_cutover == 3
    assert counts.unrepaired == 1
    await engine.dispose()
