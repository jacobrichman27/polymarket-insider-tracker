"""Receipt stub must not claim ok without locators / onchain_direction."""

from __future__ import annotations

from datetime import timedelta

import pytest

from polymarket_insider_tracker.config import ArchiveSettings
from polymarket_insider_tracker.ingestor.archive.enrichment import ArmContext, BudgetLedger
from polymarket_insider_tracker.ingestor.archive.enrichment_arms import run_receipt_arm
from tests.ingestor.featured_enrichment_harness import memory_factory, stamp, trade_row


@pytest.mark.asyncio
async def test_receipt_arm_stays_pending_without_locators() -> None:
    engine, factory, _ = await memory_factory()
    ts = stamp()
    async with factory() as session:
        trade = trade_row(observation_id="obs-r", trade_ts=ts)
        session.add(trade)
        await session.flush()
        archive = ArchiveSettings(ARCHIVE_ENABLED=True, ARCHIVE_FEATURING_ENABLED=True)
        context = ArmContext(
            session=session,
            trade=trade,
            archive=archive,
            ledger=BudgetLedger.from_settings(archive),
        )
        status = await run_receipt_arm(context)
        assert status == "pending"
        assert trade.receipt_status == "pending"
        assert trade.log_index is None
        assert trade.block_number is None
        assert trade.onchain_direction is None
    await engine.dispose()


@pytest.mark.asyncio
async def test_receipt_arm_fails_without_tx_hash() -> None:
    engine, factory, _ = await memory_factory()
    ts = stamp() - timedelta(seconds=1)
    async with factory() as session:
        trade = trade_row(observation_id="obs-notx", trade_ts=ts, tx="")
        session.add(trade)
        await session.flush()
        archive = ArchiveSettings(ARCHIVE_ENABLED=True, ARCHIVE_FEATURING_ENABLED=True)
        context = ArmContext(
            session=session,
            trade=trade,
            archive=archive,
            ledger=BudgetLedger.from_settings(archive),
        )
        assert await run_receipt_arm(context) == "failed"
    await engine.dispose()
