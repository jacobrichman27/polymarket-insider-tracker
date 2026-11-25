"""Archive markets/repair settings must not change assessment-isolation surface."""

from __future__ import annotations

from polymarket_insider_tracker.config import Settings
from tests.test_config import env_context


def test_archive_flags_do_not_disable_assessment_persist_default() -> None:
    with env_context(
        {
            "DATABASE_URL": "postgresql+psycopg://user:pass@localhost/db",
            "ARCHIVE_ENABLED": "true",
            "ARCHIVE_OUTCOME_REPAIR_ENABLED": "true",
            "ARCHIVE_KNOWABILITY_MODEL_ENABLED": "true",
        },
        clear=True,
    ):
        settings = Settings()
    assert settings.detector.persist_assessments is True
