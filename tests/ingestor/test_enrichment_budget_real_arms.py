"""Budget ledger under async default arm runners (not only the simulator)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from polymarket_insider_tracker.config import ArchiveSettings
from polymarket_insider_tracker.ingestor.archive.enrichment import ArmContext, BudgetLedger
from polymarket_insider_tracker.ingestor.archive.enrichment_arms import default_arm_runners
from tests.ingestor.featured_enrichment_harness import market_row, memory_factory, stamp, trade_row


@pytest.mark.asyncio
async def test_rpc_cap_skips_receipt_and_funding() -> None:
    engine, factory, _ = await memory_factory()
    ts = stamp()
    async with factory() as session:
        session.add(market_row(condition_id="cond-1", known_at=ts - timedelta(minutes=1)))
        trade = trade_row(observation_id="obs-rpc", trade_ts=ts)
        session.add(trade)
        await session.flush()
        archive = ArchiveSettings(
            ARCHIVE_ENABLED=True,
            ARCHIVE_FEATURING_ENABLED=True,
            ARCHIVE_ENRICHMENT_RPC_CAP=0,
        )
        ledger = BudgetLedger.from_settings(archive)
        context = ArmContext(session=session, trade=trade, archive=archive, ledger=ledger)
        runners = default_arm_runners()
        assert await runners["markets"](context) == "partial"
        assert await runners["receipt"](context) == "skipped_budget"
        # Stub funding does not burn RPC; real Transfer-log spend lands later.
        assert await runners["funding"](context) == "pending"
    await engine.dispose()


@pytest.mark.asyncio
async def test_hydrate_page_cap_skips_hydrate() -> None:
    engine, factory, _ = await memory_factory()
    ts = stamp()
    async with factory() as session:
        trade = trade_row(observation_id="obs-hyd", trade_ts=ts)
        session.add(trade)
        await session.flush()
        archive = ArchiveSettings(
            ARCHIVE_ENABLED=True,
            ARCHIVE_FEATURING_ENABLED=True,
            ARCHIVE_ENRICHMENT_HYDRATE_PAGES=0,
        )
        ledger = BudgetLedger.from_settings(archive)
        context = ArmContext(session=session, trade=trade, archive=archive, ledger=ledger)
        assert await default_arm_runners()["hydrate"](context) == "skipped_budget"
    await engine.dispose()


@pytest.mark.asyncio
async def test_markets_still_runs_when_rpc_exhausted() -> None:
    engine, factory, _ = await memory_factory()
    ts = stamp()
    async with factory() as session:
        session.add(market_row(condition_id="cond-1", known_at=ts - timedelta(minutes=1)))
        trade = trade_row(observation_id="obs-m", trade_ts=ts)
        session.add(trade)
        await session.flush()
        archive = ArchiveSettings(
            ARCHIVE_ENABLED=True,
            ARCHIVE_FEATURING_ENABLED=True,
            ARCHIVE_ENRICHMENT_RPC_CAP=0,
        )
        ledger = BudgetLedger.from_settings(archive)
        context = ArmContext(session=session, trade=trade, archive=archive, ledger=ledger)
        assert await default_arm_runners()["markets"](context) == "partial"
    await engine.dispose()
