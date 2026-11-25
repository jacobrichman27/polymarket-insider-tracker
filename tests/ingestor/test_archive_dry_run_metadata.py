"""Dry-run + archive may persist markets/knowability metadata without notifications."""

from __future__ import annotations

from polymarket_insider_tracker.config import Settings
from tests.test_config import env_context


def test_dry_run_with_archive_and_repair_flags_load() -> None:
    with env_context(
        {
            "DATABASE_URL": "postgresql+psycopg://user:pass@localhost/db",
            "DRY_RUN": "true",
            "ARCHIVE_ENABLED": "true",
            "ARCHIVE_OUTCOME_REPAIR_ENABLED": "true",
        },
        clear=True,
    ):
        settings = Settings()
    assert settings.dry_run is True
    assert settings.archive.enabled is True
    assert settings.archive.outcome_repair_effectively_enabled is True
    assert settings.discord.enabled is False
    assert settings.telegram.enabled is False
