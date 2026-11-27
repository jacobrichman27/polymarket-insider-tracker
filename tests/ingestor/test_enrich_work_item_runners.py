"""enrich_work_item + default_arm_runners end-to-end on stub arms."""

from __future__ import annotations

from datetime import timedelta

import pytest

from polymarket_insider_tracker.config import ArchiveSettings
from polymarket_insider_tracker.ingestor.archive.enrichment import enrich_work_item
from polymarket_insider_tracker.ingestor.archive.enrichment_arms import default_arm_runners
from polymarket_insider_tracker.storage.models import EnrichmentWorkItemModel, TradeModel
from polymarket_insider_tracker.storage.repos import FeaturingEnrichmentRepository
from tests.ingestor.featured_enrichment_harness import market_row, memory_factory, stamp, trade_row


@pytest.mark.asyncio
async def test_enrich_work_item_persists_stub_arm_statuses() -> None:
    engine, factory, _ = await memory_factory()
    ts = stamp()
    async with factory() as session:
        session.add(market_row(condition_id="cond-1", known_at=ts - timedelta(hours=1)))
        session.add(trade_row(observation_id="obs-1", trade_ts=ts))
        await session.flush()
        work = EnrichmentWorkItemModel(
            observation_id="obs-1",
            trade_ts=ts,
            enrichment_budget_version="b.v1",
            status="claimed",
            trigger="insert_time",
            enqueued_at=ts,
        )
        session.add(work)
        await session.flush()
        archive = ArchiveSettings(ARCHIVE_ENABLED=True, ARCHIVE_FEATURING_ENABLED=True)
        result = await enrich_work_item(
            session, work, archive=archive, runners=default_arm_runners()
        )
        await session.commit()
        assert result.statuses["markets"] == "partial"
        assert result.statuses["receipt"] == "pending"
        assert result.statuses["funding"] == "pending"
        assert result.statuses["hydrate"] == "pending"
        trade = await session.get(TradeModel, {"trade_ts": ts, "observation_id": "obs-1"})
        assert trade is not None
        assert trade.receipt_status == "pending"
        assert trade.gamma_enrichment_status == "partial"
        assert trade.funding_lookup_status == "pending"
        assert trade.wallet_hydrate_status == "pending"
        assert trade.fill_fingerprint is not None
    await engine.dispose()


@pytest.mark.asyncio
async def test_markets_failed_when_no_market_row() -> None:
    engine, factory, _ = await memory_factory()
    ts = stamp()
    async with factory() as session:
        session.add(trade_row(observation_id="obs-miss", trade_ts=ts))
        work = EnrichmentWorkItemModel(
            observation_id="obs-miss",
            trade_ts=ts,
            enrichment_budget_version="b.v1",
            status="claimed",
            trigger="insert_time",
            enqueued_at=ts,
        )
        session.add(work)
        await session.flush()
        archive = ArchiveSettings(ARCHIVE_ENABLED=True, ARCHIVE_FEATURING_ENABLED=True)
        result = await enrich_work_item(
            session, work, archive=archive, runners=default_arm_runners()
        )
        assert result.statuses["markets"] == "failed"
    await engine.dispose()


@pytest.mark.asyncio
async def test_arm_statuses_round_trip_via_repo() -> None:
    engine, factory, _ = await memory_factory()
    ts = stamp()
    async with factory() as session:
        session.add(market_row(condition_id="cond-1", known_at=ts - timedelta(minutes=1)))
        session.add(trade_row(observation_id="obs-rt", trade_ts=ts))
        work = EnrichmentWorkItemModel(
            observation_id="obs-rt",
            trade_ts=ts,
            enrichment_budget_version="b.v1",
            status="claimed",
            trigger="insert_time",
            enqueued_at=ts,
        )
        session.add(work)
        await session.flush()
        archive = ArchiveSettings(ARCHIVE_ENABLED=True, ARCHIVE_FEATURING_ENABLED=True)
        await enrich_work_item(session, work, archive=archive, runners=default_arm_runners())
        await FeaturingEnrichmentRepository(session).update_arm_statuses(
            observation_id="obs-rt",
            trade_ts=ts,
            gamma_status="partial",
            receipt_status="pending",
            funding_status="pending",
            hydrate_status="pending",
        )
        await session.commit()
        trade = await session.get(TradeModel, {"trade_ts": ts, "observation_id": "obs-rt"})
        assert trade is not None
        assert trade.receipt_status == "pending"
    await engine.dispose()
