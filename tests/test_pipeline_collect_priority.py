"""ARCHIVE_COLLECT_PRIORITY skips size-anomaly CLOB work on the trade hot path."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from polymarket_insider_tracker.config import ArchiveSettings, Settings
from polymarket_insider_tracker.pipeline import Pipeline
from tests.test_config import env_context


class _BoomSizeDetector:
    def evaluate(self, *_a: object, **_k: object) -> object:
        raise AssertionError("size anomaly must not run under collect priority")


@pytest.mark.asyncio
async def test_collect_priority_skips_size_anomaly_detector() -> None:
    with env_context(
        {
            "DATABASE_URL": "postgresql+psycopg://user:pass@localhost/db",
            "ARCHIVE_ENABLED": "true",
            "ARCHIVE_COLLECT_PRIORITY": "true",
        },
        clear=True,
    ):
        settings = Settings()
    assert settings.archive.collect_priority_effectively_enabled is True
    pipeline = Pipeline(settings, dry_run=True)
    installed = SimpleNamespace(current=SimpleNamespace(size_anomaly_detector=_BoomSizeDetector()))
    result, error = await pipeline._detect_size_anomaly(  # noqa: SLF001
        object(),  # unused when collect priority short-circuits
        datetime.now(UTC),
        installed,  # type: ignore[arg-type]
    )
    assert result is None
    assert error is None


def test_collect_priority_off_keeps_effective_false_without_archive() -> None:
    archive = ArchiveSettings.model_validate(
        {"ARCHIVE_ENABLED": False, "ARCHIVE_COLLECT_PRIORITY": True}
    )
    assert archive.collect_priority is True
    assert archive.collect_priority_effectively_enabled is False
