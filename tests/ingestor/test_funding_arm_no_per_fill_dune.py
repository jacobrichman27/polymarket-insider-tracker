"""Funding arm stub: no Dune, no RPC burn, pending honesty."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from polymarket_insider_tracker.config import ArchiveSettings
from polymarket_insider_tracker.ingestor.archive import funding_sync
from polymarket_insider_tracker.ingestor.archive.enrichment import ArmContext, BudgetLedger
from polymarket_insider_tracker.storage.models import ProxyFundingModel
from tests.ingestor.featured_enrichment_harness import memory_factory, stamp, trade_row


@pytest.mark.asyncio
async def test_funding_arm_writes_pending_stub_without_rpc() -> None:
    assert not hasattr(funding_sync, "run_dune_lookup")
    engine, factory, _ = await memory_factory()
    ts = stamp()
    async with factory() as session:
        trade = trade_row(observation_id="obs-f", trade_ts=ts)
        session.add(trade)
        await session.flush()
        archive = ArchiveSettings(ARCHIVE_ENABLED=True, ARCHIVE_FEATURING_ENABLED=True)
        ledger = BudgetLedger.from_settings(archive)
        context = ArmContext(session=session, trade=trade, archive=archive, ledger=ledger)
        status = await funding_sync.run_funding_arm(context)
        assert status == "pending"
        assert ledger.rpc_used == 0
        row = (
            await session.execute(
                select(ProxyFundingModel).where(
                    ProxyFundingModel.proxy_wallet == trade.proxy_wallet
                )
            )
        ).scalar_one()
        assert row.funding_lookup_status == "pending"
        assert row.funding_source is None
        assert row.first_funding_exact is None
        assert row.payload == {"writer": "transfer_logs_stub"}
    await engine.dispose()
