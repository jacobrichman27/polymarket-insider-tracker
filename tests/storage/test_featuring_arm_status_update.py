"""Persist and read per-arm enrichment statuses."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from polymarket_insider_tracker.storage.models import Base, TradeModel
from polymarket_insider_tracker.storage.repos import FeaturingEnrichmentRepository


@pytest.mark.asyncio
async def test_update_arm_statuses_round_trip() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    trade_ts = datetime.now(UTC)
    async with factory() as session:
        session.add(
            TradeModel(
                trade_ts=trade_ts,
                observation_id="obs-arm",
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
        )
        await session.commit()
        repo = FeaturingEnrichmentRepository(session)
        await repo.update_arm_statuses(
            observation_id="obs-arm",
            trade_ts=trade_ts,
            gamma_status="ok",
            receipt_status="pending",
            funding_status="miss",
            hydrate_status="skipped_budget",
        )
        await session.commit()
        trade = await session.get(TradeModel, {"trade_ts": trade_ts, "observation_id": "obs-arm"})
        assert trade is not None
        assert trade.gamma_enrichment_status == "ok"
        assert trade.receipt_status == "pending"
        assert trade.funding_lookup_status == "miss"
        assert trade.wallet_hydrate_status == "skipped_budget"
    await engine.dispose()
