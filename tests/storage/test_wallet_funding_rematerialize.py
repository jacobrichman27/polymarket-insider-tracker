"""Wallets / proxy_funding rematerialize joins."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from polymarket_insider_tracker.storage.models import ArchiveWalletModel, Base, ProxyFundingModel
from polymarket_insider_tracker.storage.repos import FeaturingEnrichmentRepository


@pytest.mark.asyncio
async def test_as_of_joins_use_known_at_not_after_trade() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    trade_ts = datetime(2026, 11, 20, tzinfo=UTC)
    async with factory() as session:
        session.add(
            ArchiveWalletModel(
                proxy_wallet="0xabc",
                known_at=trade_ts - timedelta(days=1),
                wallet_hydrate_status="ok",
            )
        )
        session.add(
            ArchiveWalletModel(
                proxy_wallet="0xabc",
                known_at=trade_ts + timedelta(days=1),
                wallet_hydrate_status="ok",
            )
        )
        session.add(
            ProxyFundingModel(
                proxy_wallet="0xabc",
                known_at=trade_ts - timedelta(hours=1),
                funding_lookup_status="ok",
            )
        )
        await session.commit()
        repo = FeaturingEnrichmentRepository(session)
        wallet = await repo.wallet_as_of("0xabc", trade_ts)
        funding = await repo.funding_as_of("0xabc", trade_ts)
        assert wallet is not None
        assert funding is not None
        assert wallet.known_at.replace(tzinfo=UTC) <= trade_ts
        assert funding.known_at.replace(tzinfo=UTC) <= trade_ts
        assert wallet.known_at.replace(tzinfo=UTC) == trade_ts - timedelta(days=1)
    await engine.dispose()
