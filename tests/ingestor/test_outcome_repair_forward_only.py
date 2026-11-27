"""Forward-only outcome repair cutover and never-invent (US1)."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from polymarket_insider_tracker.ingestor.archive.markets import append_market_version
from polymarket_insider_tracker.ingestor.archive.outcome_repair import (
    decide_repair,
    repair_trade_row,
)
from polymarket_insider_tracker.storage.models import Base, TradeModel

SessionFactory = async_sessionmaker[AsyncSession]


def _trade(
    *,
    trade_ts: datetime,
    observation_id: str,
    outcome: str | None,
    outcome_index: int | None,
    status: str = "not_attempted",
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


@pytest.fixture
async def session_factory() -> AsyncGenerator[SessionFactory, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory: SessionFactory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


def test_decide_repair_never_invents_on_thin_without_map() -> None:
    decision = decide_repair(
        outcome=None,
        outcome_index=999,
        token_id="tok",
        token_outcomes={},
    )
    assert decision.status == "unrepaired"
    assert decision.outcome_repaired is None


def test_decide_repair_usable_api_is_not_needed() -> None:
    decision = decide_repair(
        outcome="Yes",
        outcome_index=0,
        token_id="tok",
        token_outcomes={"tok": {"outcome": "No", "outcome_index": 1}},
    )
    assert decision.status == "not_needed"
    assert decision.outcome_repaired is None


def test_decide_repair_raw_999_not_treated_as_usable_api() -> None:
    decision = decide_repair(
        outcome="Yes",
        outcome_index=0,
        token_id="tok",
        token_outcomes={"tok": {"outcome": "Yes", "outcome_index": 0}},
        raw_outcome_index=999,
    )
    assert decision.status == "ok"
    assert decision.outcome_repaired == "Yes"
    assert decision.outcome_index_repaired == 0


@pytest.mark.asyncio
async def test_pre_cutover_rows_untouched(session_factory: SessionFactory) -> None:
    cutover = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)
    early = cutover - timedelta(hours=1)
    async with session_factory() as session:
        session.add(
            _trade(trade_ts=early, observation_id="obs-early", outcome=None, outcome_index=999)
        )
        await session.commit()
        result = await repair_trade_row(
            session,
            trade_ts=early,
            observation_id="obs-early",
            observed_at=early,
            condition_id="c1",
            token_id="tok",
            outcome=None,
            outcome_index=999,
            repair_enabled_at=cutover,
        )
        await session.commit()
        assert result is None
        row = (
            await session.execute(
                select(TradeModel).where(TradeModel.observation_id == "obs-early")
            )
        ).scalar_one()
        assert row.outcome_repair_status == "not_attempted"


@pytest.mark.asyncio
async def test_post_cutover_thin_maps_to_ok(session_factory: SessionFactory) -> None:
    cutover = datetime(2026, 11, 24, 12, 0, tzinfo=UTC)
    trade_ts = cutover + timedelta(minutes=5)
    async with session_factory() as session:
        await append_market_version(
            session,
            condition_id="c1",
            token_outcomes={"tok": {"outcome": "Yes", "outcome_index": 0}},
            known_at=cutover,
        )
        session.add(
            _trade(trade_ts=trade_ts, observation_id="obs-late", outcome="", outcome_index=999)
        )
        await session.commit()
        decision = await repair_trade_row(
            session,
            trade_ts=trade_ts,
            observation_id="obs-late",
            observed_at=trade_ts,
            condition_id="c1",
            token_id="tok",
            outcome="",
            outcome_index=999,
            repair_enabled_at=cutover,
        )
        await session.commit()
        assert decision is not None
        assert decision.status == "ok"
        assert decision.outcome_repaired == "Yes"
        row = (
            await session.execute(select(TradeModel).where(TradeModel.observation_id == "obs-late"))
        ).scalar_one()
        assert row.outcome_repair_status == "ok"
