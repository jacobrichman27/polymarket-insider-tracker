"""Shared in-memory DB helpers for featured enrichment orchestration tests."""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from polymarket_insider_tracker.ingestor.archive.knowability import KNOWABILITY_POLICY_VERSION
from polymarket_insider_tracker.storage.models import Base, MarketVersionModel, TradeModel


def trade_row(
    *,
    observation_id: str,
    trade_ts: datetime,
    tx: str = "0xabc",
    wallet: str = "0xw1",
    condition_id: str = "cond-1",
    token_id: str = "tok-1",
    price: str = "0.55",
    size: str = "10000",
    receipt_status: str = "not_attempted",
) -> TradeModel:
    return TradeModel(
        trade_ts=trade_ts,
        observation_id=observation_id,
        observed_at=trade_ts,
        archive_start_at=trade_ts,
        source_id="src",
        transaction_hash=tx,
        proxy_wallet=wallet,
        condition_id=condition_id,
        token_id=token_id,
        outcome="Yes",
        outcome_index=0,
        side="BUY",
        price=Decimal(price),
        size_shares=Decimal(size),
        notional_usdc=Decimal(price) * Decimal(size),
        source="test",
        neg_risk=None,
        outcome_repair_status="not_needed",
        outcome_repaired=None,
        outcome_index_repaired=None,
        receipt_status=receipt_status,
        info_knowability_regime="private_edge_possible",
        knowability_label_source="test",
        raw_row_json={"price": price},
    )


def market_row(
    *,
    condition_id: str,
    known_at: datetime,
    regime: str = "private_edge_possible",
    policy_version: str = KNOWABILITY_POLICY_VERSION,
) -> MarketVersionModel:
    return MarketVersionModel(
        condition_id=condition_id,
        known_at=known_at,
        token_outcomes={"tok-1": "Yes"},
        question="q",
        series_slug=None,
        info_knowability_regime=regime,
        knowable_from=None,
        knowability_label_source="test",
        knowability_policy_version=policy_version,
        source_version="t",
        raw_market_json=None,
    )


class MemorySessionFactory:
    """Minimal SessionFactory for enrichment_loop / enqueue helpers."""

    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory

    def get_async_session(self) -> AbstractAsyncContextManager[AsyncSession]:
        return self._factory()


async def memory_factory() -> tuple[object, async_sessionmaker[AsyncSession], MemorySessionFactory]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, factory, MemorySessionFactory(factory)


def stamp() -> datetime:
    return datetime(2026, 11, 25, 12, 0, 0, tzinfo=UTC)
