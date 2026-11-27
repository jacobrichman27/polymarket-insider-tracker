"""Dry-run + featuring may write research rows without notification delivery."""

from __future__ import annotations

from polymarket_insider_tracker.config import ArchiveSettings, Settings
from polymarket_insider_tracker.ingestor.archive.featuring import should_run_featuring_workers
from tests.test_config import env_context


def test_dry_run_does_not_disable_featuring_research_writes() -> None:
    with env_context(
        {
            "DATABASE_URL": "postgresql+psycopg://user:pass@localhost/db",
            "DRY_RUN": "true",
            "ARCHIVE_ENABLED": "true",
            "ARCHIVE_FEATURING_ENABLED": "true",
        },
        clear=True,
    ):
        settings = Settings()
    assert settings.dry_run is True
    assert should_run_featuring_workers(settings.archive) is True


def test_featuring_settings_are_not_delivery_channels() -> None:
    names = set(ArchiveSettings.model_fields)
    assert "discord" not in names
    assert "telegram" not in names
