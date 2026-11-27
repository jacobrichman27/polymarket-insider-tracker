"""Archive and outcome-repair health checkers register when flags are on."""

from __future__ import annotations

import pytest

from polymarket_insider_tracker.config import ArchiveSettings, Settings
from polymarket_insider_tracker.pipeline import Pipeline
from tests.fakes import make_test_settings


def _archive_on_settings() -> Settings:
    base = make_test_settings(archive_enabled=True)
    archive = ArchiveSettings.model_validate(
        {
            "ARCHIVE_ENABLED": True,
            "ARCHIVE_OUTCOME_REPAIR_ENABLED": True,
            "ARCHIVE_FEATURING_ENABLED": True,
        }
    )
    return base.model_copy(update={"archive": archive})


@pytest.mark.asyncio
async def test_archive_and_repair_health_checkers_wire() -> None:
    pipeline = Pipeline(_archive_on_settings())
    components = await pipeline.health_monitor.evaluate_components()
    assert "trade_archive" in components
    assert "outcome_repair" in components
    assert "featured_enrichment" in components
    assert components["trade_archive"].status in {"up", "degraded", "down"}
    assert components["outcome_repair"].status in {"up", "degraded", "down"}
    assert components["featured_enrichment"].status in {"up", "degraded"}
