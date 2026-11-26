"""Regime upgrade must not rewrite historical trades knowability columns."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from polymarket_insider_tracker.ingestor.archive.markets import append_market_version
from polymarket_insider_tracker.storage.models import Base, TradeModel


@pytest.mark.asyncio
async def test_markets_upgrade_leaves_trade_knowability_untouched() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    t0 = datetime(2026, 11, 20, tzinfo=UTC)
    async with factory() as session:
        await append_market_version(
            session,
            condition_id="c1",
            token_outcomes={"t": {"outcome": "Yes", "outcome_index": 0}},
            known_at=t0,
            info_knowability_regime="unknown",
            knowability_label_source="unknown",
        )
        session.add(
            TradeModel(
                trade_ts=t0,
                observation_id="obs-1",
                observed_at=t0,
                archive_start_at=t0,
                source_id="src",
                transaction_hash="0x1",
                proxy_wallet="0xabc",
                condition_id="c1",
                token_id="t",
                outcome="Yes",
                outcome_index=0,
                side="BUY",
                price=Decimal("0.5"),
                size_shares=Decimal("1"),
                notional_usdc=Decimal("0.5"),
                source="api",
                neg_risk=None,
                outcome_repair_status="not_needed",
                outcome_repaired=None,
                outcome_index_repaired=None,
                receipt_status="unknown",
                info_knowability_regime="unknown",
                knowability_label_source="unknown",
                raw_row_json=None,
            )
        )
        await session.commit()
        await append_market_version(
            session,
            condition_id="c1",
            token_outcomes={"t": {"outcome": "Yes", "outcome_index": 0}},
            known_at=t0 + timedelta(hours=1),
            info_knowability_regime="private_edge_possible",
            knowability_label_source="model",
        )
        await session.commit()
        trade = await session.get(TradeModel, {"trade_ts": t0, "observation_id": "obs-1"})
        assert trade is not None
        assert trade.info_knowability_regime == "unknown"
        assert trade.knowability_label_source == "unknown"
    await engine.dispose()
