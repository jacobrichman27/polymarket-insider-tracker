"""Receipt path: fingerprint always; live_as_of only after receipt ok/partial."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from polymarket_insider_tracker.config import ArchiveSettings
from polymarket_insider_tracker.ingestor.archive.enrichment import ArmContext, BudgetLedger
from polymarket_insider_tracker.ingestor.archive.enrichment_arms import (
    _run_receipt_and_fingerprint,
    apply_observation_fingerprint,
)
from polymarket_insider_tracker.storage.models import TradeFeaturesModel
from tests.ingestor.featured_enrichment_harness import memory_factory, stamp, trade_row


@pytest.mark.asyncio
async def test_pending_receipt_fingerprints_without_live_as_of() -> None:
    engine, factory, _ = await memory_factory()
    ts = stamp()
    async with factory() as session:
        trade = trade_row(observation_id="obs-tf", trade_ts=ts)
        session.add(trade)
        await session.flush()
        archive = ArchiveSettings(ARCHIVE_ENABLED=True, ARCHIVE_FEATURING_ENABLED=True)
        context = ArmContext(
            session=session,
            trade=trade,
            archive=archive,
            ledger=BudgetLedger.from_settings(archive),
        )
        status = await _run_receipt_and_fingerprint(context)
        assert status == "pending"
        assert trade.fill_fingerprint is not None
        rows = (
            (
                await session.execute(
                    select(TradeFeaturesModel).where(TradeFeaturesModel.observation_id == "obs-tf")
                )
            )
            .scalars()
            .all()
        )
        assert rows == []
    await engine.dispose()


@pytest.mark.asyncio
async def test_ok_receipt_live_as_of_immutable() -> None:
    engine, factory, _ = await memory_factory()
    ts = stamp()
    async with factory() as session:
        trade = trade_row(observation_id="obs-ok", trade_ts=ts)
        session.add(trade)
        await session.flush()
        archive = ArchiveSettings(ARCHIVE_ENABLED=True, ARCHIVE_FEATURING_ENABLED=True)
        context = ArmContext(
            session=session,
            trade=trade,
            archive=archive,
            ledger=BudgetLedger.from_settings(archive),
        )
        trade.receipt_status = "ok"
        await apply_observation_fingerprint(context, receipt_status="ok")
        first = (
            await session.execute(
                select(TradeFeaturesModel).where(TradeFeaturesModel.observation_id == "obs-ok")
            )
        ).scalar_one()
        assert first.order_as_of_contract == "live_as_of"
        assert isinstance(first.payload, dict)
        assert "strength" in first.payload
        trade.log_index = 1
        await apply_observation_fingerprint(context, receipt_status="ok")
        live = (
            (
                await session.execute(
                    select(TradeFeaturesModel).where(TradeFeaturesModel.observation_id == "obs-ok")
                )
            )
            .scalars()
            .all()
        )
        assert len(live) == 1
        assert live[0].payload == first.payload
    await engine.dispose()
