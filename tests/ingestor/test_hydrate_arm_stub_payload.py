"""Hydrate stub honesty: stub payload + no false first-trade Core claim."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from polymarket_insider_tracker.config import ArchiveSettings
from polymarket_insider_tracker.ingestor.archive.enrichment import ArmContext, BudgetLedger
from polymarket_insider_tracker.ingestor.archive.wallet_hydrate import (
    lifetime_is_first_trade_value,
    run_hydrate_arm,
)
from polymarket_insider_tracker.storage.models import ArchiveWalletModel
from tests.ingestor.featured_enrichment_harness import memory_factory, stamp, trade_row


@pytest.mark.asyncio
async def test_hydrate_stub_marks_payload_and_null_first_trade() -> None:
    engine, factory, _ = await memory_factory()
    ts = stamp()
    async with factory() as session:
        trade = trade_row(observation_id="obs-h", trade_ts=ts)
        session.add(trade)
        await session.flush()
        archive = ArchiveSettings(ARCHIVE_ENABLED=True, ARCHIVE_FEATURING_ENABLED=True)
        context = ArmContext(
            session=session,
            trade=trade,
            archive=archive,
            ledger=BudgetLedger.from_settings(archive),
        )
        status = await run_hydrate_arm(context)
        assert status == "pending"
        row = (
            await session.execute(
                select(ArchiveWalletModel).where(
                    ArchiveWalletModel.proxy_wallet == trade.proxy_wallet
                )
            )
        ).scalar_one()
        assert row.wallet_hydrate_status == "pending"
        assert row.payload == {"source": "data_api_stub"}
        assert row.lifetime_is_first_trade is None
        assert lifetime_is_first_trade_value(complete=True, empty_walk=False) is None
        # known_at is observe-time, not trade_ts (as-of rematerialize uses latest ≤ trade_ts).
        assert row.known_at.replace(tzinfo=None) >= ts.replace(tzinfo=None)
    await engine.dispose()
