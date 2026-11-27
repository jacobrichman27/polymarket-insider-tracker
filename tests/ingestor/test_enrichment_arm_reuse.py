"""Shared-arm reuse by tx (receipt) and proxy (funding/hydrate)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from polymarket_insider_tracker.config import ArchiveSettings
from polymarket_insider_tracker.ingestor.archive.enrichment import enrich_work_item
from polymarket_insider_tracker.ingestor.archive.enrichment_arms import default_arm_runners
from polymarket_insider_tracker.storage.models import EnrichmentWorkItemModel, TradeModel
from tests.ingestor.featured_enrichment_harness import market_row, memory_factory, stamp, trade_row


@pytest.mark.asyncio
async def test_second_leg_reuses_receipt_without_second_rpc() -> None:
    engine, factory, _ = await memory_factory()
    ts = stamp()
    async with factory() as session:
        session.add(market_row(condition_id="cond-1", known_at=ts - timedelta(hours=1)))
        session.add(trade_row(observation_id="obs-a", trade_ts=ts, wallet="0xw1", price="0.4"))
        session.add(
            trade_row(
                observation_id="obs-b",
                trade_ts=ts,
                wallet="0xw2",
                price="0.6",
                size="5000",
            )
        )
        await session.flush()
        archive = ArchiveSettings(ARCHIVE_ENABLED=True, ARCHIVE_FEATURING_ENABLED=True)
        work_a = EnrichmentWorkItemModel(
            observation_id="obs-a",
            trade_ts=ts,
            enrichment_budget_version="b.v1",
            status="claimed",
            trigger="insert_time",
            enqueued_at=ts,
        )
        session.add(work_a)
        await session.flush()
        first = await enrich_work_item(
            session, work_a, archive=archive, runners=default_arm_runners()
        )
        assert first.statuses["receipt"] == "pending"
        work_b = EnrichmentWorkItemModel(
            observation_id="obs-b",
            trade_ts=ts,
            enrichment_budget_version="b.v1",
            status="claimed",
            trigger="insert_time",
            enqueued_at=ts,
        )
        session.add(work_b)
        await session.flush()
        # Force RPC empty: reuse must still return pending without needing spend.
        archive_tight = ArchiveSettings(
            ARCHIVE_ENABLED=True,
            ARCHIVE_FEATURING_ENABLED=True,
            ARCHIVE_ENRICHMENT_RPC_CAP=0,
        )
        second = await enrich_work_item(
            session, work_b, archive=archive_tight, runners=default_arm_runners()
        )
        assert second.statuses["receipt"] == "pending"
        assert second.statuses["markets"] in {"partial", "failed"}
        trade_b = await session.get(TradeModel, {"trade_ts": ts, "observation_id": "obs-b"})
        assert trade_b is not None
        assert trade_b.fill_fingerprint is not None
    await engine.dispose()


@pytest.mark.asyncio
async def test_same_proxy_reuses_funding_and_hydrate_status() -> None:
    engine, factory, _ = await memory_factory()
    ts = stamp()
    later = ts + timedelta(minutes=1)
    async with factory() as session:
        session.add(market_row(condition_id="cond-1", known_at=ts - timedelta(hours=1)))
        session.add(trade_row(observation_id="obs-p1", trade_ts=ts, wallet="0xsame"))
        session.add(
            trade_row(
                observation_id="obs-p2",
                trade_ts=later,
                wallet="0xsame",
                tx="0xdef",
            )
        )
        await session.flush()
        archive = ArchiveSettings(ARCHIVE_ENABLED=True, ARCHIVE_FEATURING_ENABLED=True)
        for obs, when in (("obs-p1", ts), ("obs-p2", later)):
            work = EnrichmentWorkItemModel(
                observation_id=obs,
                trade_ts=when,
                enrichment_budget_version="b.v1",
                status="claimed",
                trigger="insert_time",
                enqueued_at=when,
            )
            session.add(work)
            await session.flush()
            result = await enrich_work_item(
                session, work, archive=archive, runners=default_arm_runners()
            )
            assert result.statuses["funding"] == "pending"
            assert result.statuses["hydrate"] == "pending"
    await engine.dispose()
