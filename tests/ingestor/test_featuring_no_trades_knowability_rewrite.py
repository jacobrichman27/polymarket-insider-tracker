"""Featuring backfill must not rewrite trades knowability columns."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from polymarket_insider_tracker.config import ArchiveSettings
from polymarket_insider_tracker.ingestor.archive.featuring import enqueue_hot_backfill_for_market
from polymarket_insider_tracker.storage.models import Base, TradeModel


@pytest.mark.asyncio
async def test_backfill_preserves_trades_knowability_columns() -> None:
    now = datetime(2026, 11, 25, tzinfo=UTC)
    trade_ts = now - timedelta(days=1)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add(
            TradeModel(
                trade_ts=trade_ts,
                observation_id="obs-k",
                observed_at=trade_ts,
                archive_start_at=trade_ts,
                source_id="src",
                transaction_hash="0xtx",
                proxy_wallet="0xabc",
                condition_id="cond-k",
                token_id="tok",
                outcome=None,
                outcome_index=None,
                side="BUY",
                price=Decimal("0.5"),
                size_shares=Decimal("20000"),
                notional_usdc=Decimal("10000"),
                source="test",
                neg_risk=None,
                outcome_repair_status="not_needed",
                outcome_repaired=None,
                outcome_index_repaired=None,
                receipt_status="not_attempted",
                info_knowability_regime="unknown",
                knowability_label_source="provisional",
                raw_row_json=None,
            )
        )
        await session.commit()
        archive = ArchiveSettings(ARCHIVE_ENABLED=True, ARCHIVE_FEATURING_ENABLED=True)
        await enqueue_hot_backfill_for_market(
            session,
            condition_id="cond-k",
            new_regime="private_edge_possible",
            archive=archive,
            now=now,
        )
        await session.commit()
        trade = await session.get(TradeModel, (trade_ts, "obs-k"))
        assert trade is not None
        assert trade.info_knowability_regime == "unknown"
        assert trade.knowability_label_source == "provisional"
        trade.featuring_reason = "eligible"
        assert trade.featuring_reason == "eligible"
    await engine.dispose()
