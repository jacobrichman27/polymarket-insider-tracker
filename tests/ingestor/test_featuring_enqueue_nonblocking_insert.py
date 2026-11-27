"""Featuring enqueue is fire-and-forget relative to the caller."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from polymarket_insider_tracker.config import ArchiveSettings
from polymarket_insider_tracker.ingestor.archive.featuring import schedule_featuring_enqueue
from polymarket_insider_tracker.ingestor.trade_rows import TradeObservation, parse_trade_row
from tests.fakes.trades import trade_row as provider_row
from tests.ingestor.featured_enrichment_harness import MemorySessionFactory, memory_factory


def _observation() -> TradeObservation:
    now = int(datetime(2026, 11, 25, 12, 0, 0, tzinfo=UTC).timestamp())
    parsed = parse_trade_row(
        provider_row(timestamp=now, size="10000", price="0.55", transaction=3),
        now=now,
    )
    assert isinstance(parsed, TradeObservation)
    return parsed


@pytest.mark.asyncio
async def test_schedule_returns_while_enqueue_still_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def _slow(*_a: object, **_k: object) -> None:
        started.set()
        await release.wait()

    from polymarket_insider_tracker.ingestor.archive import featuring as featuring_mod

    monkeypatch.setattr(featuring_mod, "enqueue_after_insert", _slow)
    engine, factory, db = await memory_factory()
    archive = ArchiveSettings(ARCHIVE_ENABLED=True, ARCHIVE_FEATURING_ENABLED=True)
    loop = asyncio.get_running_loop()
    schedule_featuring_enqueue(loop, db, observation=_observation(), archive=archive)
    await asyncio.wait_for(started.wait(), timeout=1.0)
    # Caller already returned; unblock background task for clean teardown.
    release.set()
    await asyncio.sleep(0)
    await engine.dispose()


@pytest.mark.asyncio
async def test_disabled_featuring_schedule_is_noop() -> None:
    engine, factory, db = await memory_factory()
    archive = ArchiveSettings(ARCHIVE_ENABLED=True, ARCHIVE_FEATURING_ENABLED=False)
    loop = asyncio.get_running_loop()
    schedule_featuring_enqueue(loop, db, observation=_observation(), archive=archive)
    assert isinstance(db, MemorySessionFactory)
    await engine.dispose()
