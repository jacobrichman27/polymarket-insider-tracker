"""Eligible insert enqueues work; ineligible does not; errors counted."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from polymarket_insider_tracker.config import ArchiveSettings
from polymarket_insider_tracker.ingestor.archive.enrichment_health import enrichment_health
from polymarket_insider_tracker.ingestor.archive.featuring import enqueue_after_insert
from polymarket_insider_tracker.ingestor.trade_rows import TradeObservation, parse_trade_row
from polymarket_insider_tracker.storage.repos import FeaturingEnrichmentRepository
from tests.fakes.trades import trade_row as provider_row
from tests.ingestor.featured_enrichment_harness import (
    market_row,
    memory_factory,
)
from tests.ingestor.featured_enrichment_harness import (
    trade_row as tape_row,
)


def _observation(*, size: str, market: str = "cond-1") -> TradeObservation:
    now = int(datetime(2026, 11, 25, 12, 0, 0, tzinfo=UTC).timestamp())
    parsed = parse_trade_row(
        provider_row(timestamp=now, size=size, price="0.55", market=market, transaction=9),
        now=now,
    )
    assert isinstance(parsed, TradeObservation)
    return parsed


@pytest.mark.asyncio
async def test_eligible_enqueues_work_item() -> None:
    engine, factory, db = await memory_factory()
    obs = _observation(size="10000")
    ts = obs.event.timestamp
    async with factory() as session:
        session.add(market_row(condition_id=obs.event.market_id, known_at=ts - timedelta(hours=1)))
        session.add(
            tape_row(
                observation_id=obs.identity,
                trade_ts=ts,
                condition_id=obs.event.market_id,
                wallet=obs.event.wallet_address,
                tx=obs.event.trade_id,
                size="10000",
            )
        )
        await session.commit()
    archive = ArchiveSettings(ARCHIVE_ENABLED=True, ARCHIVE_FEATURING_ENABLED=True)
    decision = await enqueue_after_insert(db, observation=obs, archive=archive)
    assert decision is not None
    assert decision.eligible is True
    async with factory() as session:
        claimed = await FeaturingEnrichmentRepository(session).claim_next_pending(now=ts)
        assert claimed is not None
        assert claimed.observation_id == obs.identity
    await engine.dispose()


@pytest.mark.asyncio
async def test_legacy_policy_version_treated_as_unknown() -> None:
    engine, factory, db = await memory_factory()
    obs = _observation(size="10000")
    ts = obs.event.timestamp
    async with factory() as session:
        session.add(
            market_row(
                condition_id=obs.event.market_id,
                known_at=ts - timedelta(hours=1),
                regime="always_latent",
                policy_version="knowability.v1",
            )
        )
        session.add(
            tape_row(
                observation_id=obs.identity,
                trade_ts=ts,
                condition_id=obs.event.market_id,
                wallet=obs.event.wallet_address,
                tx=obs.event.trade_id,
                size="10000",
            )
        )
        await session.commit()
    archive = ArchiveSettings(ARCHIVE_ENABLED=True, ARCHIVE_FEATURING_ENABLED=True)
    decision = await enqueue_after_insert(db, observation=obs, archive=archive)
    assert decision is not None
    assert decision.eligible is False
    assert decision.reason == "regime_unknown"
    await engine.dispose()


@pytest.mark.asyncio
async def test_ineligible_does_not_enqueue() -> None:
    engine, factory, db = await memory_factory()
    obs = _observation(size="1")
    ts = obs.event.timestamp
    async with factory() as session:
        session.add(market_row(condition_id=obs.event.market_id, known_at=ts - timedelta(hours=1)))
        session.add(
            tape_row(
                observation_id=obs.identity,
                trade_ts=ts,
                condition_id=obs.event.market_id,
                wallet=obs.event.wallet_address,
                tx=obs.event.trade_id,
                size="1",
            )
        )
        await session.commit()
    archive = ArchiveSettings(ARCHIVE_ENABLED=True, ARCHIVE_FEATURING_ENABLED=True)
    decision = await enqueue_after_insert(db, observation=obs, archive=archive)
    assert decision is not None
    assert decision.eligible is False
    async with factory() as session:
        assert await FeaturingEnrichmentRepository(session).claim_next_pending(now=ts) is None
    await engine.dispose()


@pytest.mark.asyncio
async def test_enqueue_error_increments_metric(monkeypatch: pytest.MonkeyPatch) -> None:
    from polymarket_insider_tracker.ingestor.archive import featuring as featuring_mod

    async def _boom(*_a: object, **_k: object) -> None:
        raise RuntimeError("enqueue failed")

    monkeypatch.setattr(featuring_mod, "enqueue_after_insert", _boom)
    health = enrichment_health()
    before = health.enqueue_error_count
    obs = _observation(size="10000")
    archive = ArchiveSettings(ARCHIVE_ENABLED=True, ARCHIVE_FEATURING_ENABLED=True)
    engine, factory, db = await memory_factory()
    await featuring_mod._run_scheduled_enqueue(db, observation=obs, archive=archive)
    assert health.enqueue_error_count > before
    assert health.evaluate().status == "degraded"
    await engine.dispose()
