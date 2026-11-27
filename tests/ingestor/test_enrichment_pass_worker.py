"""One enrichment_pass claim → enrich → complete / abandon cycle."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from polymarket_insider_tracker.config import ArchiveSettings
from polymarket_insider_tracker.ingestor.archive.enrichment_health import enrichment_health
from polymarket_insider_tracker.ingestor.archive.workers import _enrichment_pass
from polymarket_insider_tracker.storage.models import EnrichmentWorkItemModel
from tests.ingestor.featured_enrichment_harness import market_row, memory_factory, stamp, trade_row


@pytest.mark.asyncio
async def test_enrichment_pass_empty_queue_noop() -> None:
    engine, factory, db = await memory_factory()
    archive = ArchiveSettings(ARCHIVE_ENABLED=True, ARCHIVE_FEATURING_ENABLED=True)
    from polymarket_insider_tracker.ingestor.archive.enrichment_arms import default_arm_runners

    await _enrichment_pass(db, archive=archive, runners=default_arm_runners())
    await engine.dispose()


@pytest.mark.asyncio
async def test_enrichment_pass_claims_and_completes() -> None:
    engine, factory, db = await memory_factory()
    ts = stamp()
    async with factory() as session:
        session.add(market_row(condition_id="cond-1", known_at=ts - timedelta(hours=1)))
        session.add(trade_row(observation_id="obs-pass", trade_ts=ts))
        from polymarket_insider_tracker.storage.repos import FeaturingEnrichmentRepository

        await FeaturingEnrichmentRepository(session).enqueue_work(
            observation_id="obs-pass",
            trade_ts=ts,
            enrichment_budget_version="b.v1",
            trigger="insert_time",
            enqueued_at=ts,
        )
        await session.commit()
    archive = ArchiveSettings(ARCHIVE_ENABLED=True, ARCHIVE_FEATURING_ENABLED=True)
    from polymarket_insider_tracker.ingestor.archive.enrichment_arms import default_arm_runners

    before = enrichment_health().attempt_count
    await _enrichment_pass(db, archive=archive, runners=default_arm_runners())
    assert enrichment_health().attempt_count >= before
    async with factory() as session:
        from polymarket_insider_tracker.storage.repos import FeaturingEnrichmentRepository
        from polymarket_insider_tracker.storage.models import EnrichmentWorkItemModel
        from sqlalchemy import select

        assert await FeaturingEnrichmentRepository(session).claim_next_pending(now=ts) is None
        work = (
            await session.execute(
                select(EnrichmentWorkItemModel).where(
                    EnrichmentWorkItemModel.observation_id == "obs-pass"
                )
            )
        ).scalar_one()
        assert work.status == "completed"
    await engine.dispose()


@pytest.mark.asyncio
async def test_enrichment_pass_abandons_when_trade_missing() -> None:
    engine, factory, db = await memory_factory()
    ts = stamp()
    async with factory() as session:
        from polymarket_insider_tracker.storage.repos import FeaturingEnrichmentRepository

        await FeaturingEnrichmentRepository(session).enqueue_work(
            observation_id="obs-ghost",
            trade_ts=ts,
            enrichment_budget_version="b.v1",
            trigger="insert_time",
            enqueued_at=ts,
        )
        await session.commit()
    archive = ArchiveSettings(ARCHIVE_ENABLED=True, ARCHIVE_FEATURING_ENABLED=True)
    from polymarket_insider_tracker.ingestor.archive.enrichment_arms import default_arm_runners

    await _enrichment_pass(db, archive=archive, runners=default_arm_runners())
    async with factory() as session:
        work = (
            await session.execute(
                select(EnrichmentWorkItemModel).where(
                    EnrichmentWorkItemModel.observation_id == "obs-ghost"
                )
            )
        ).scalar_one()
        assert work.status == "abandoned"
        assert work.last_error == "trade_missing"
    await engine.dispose()
