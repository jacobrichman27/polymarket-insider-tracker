"""Featuring fire-and-forget tasks are tracked and cancellable on shutdown."""

from __future__ import annotations

import asyncio

import pytest

from polymarket_insider_tracker.config import ArchiveSettings
from polymarket_insider_tracker.ingestor.archive.featuring import (
    cancel_featuring_background_tasks,
    schedule_featuring_enqueue,
    tracked_featuring_task_count,
)
from tests.ingestor.featured_enrichment_harness import memory_factory
from tests.ingestor.test_featuring_enqueue_after_insert import _observation


@pytest.mark.asyncio
async def test_schedule_tracks_and_cancel_clears(monkeypatch: pytest.MonkeyPatch) -> None:
    engine, _factory, db = await memory_factory()
    archive = ArchiveSettings(ARCHIVE_ENABLED=True, ARCHIVE_FEATURING_ENABLED=True)
    loop = asyncio.get_running_loop()
    gate = asyncio.Event()

    async def _hold(*_a: object, **_k: object) -> None:
        await gate.wait()

    from polymarket_insider_tracker.ingestor.archive import featuring as featuring_mod

    monkeypatch.setattr(featuring_mod, "enqueue_after_insert", _hold)
    before = tracked_featuring_task_count()
    schedule_featuring_enqueue(loop, db, observation=_observation(size="10000"), archive=archive)
    assert tracked_featuring_task_count() == before + 1
    await cancel_featuring_background_tasks()
    assert tracked_featuring_task_count() == 0
    gate.set()
    await engine.dispose()
