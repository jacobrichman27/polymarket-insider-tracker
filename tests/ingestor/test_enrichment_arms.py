"""Enrichment arm order and status honesty."""

from __future__ import annotations

from polymarket_insider_tracker.config import ArchiveSettings
from polymarket_insider_tracker.ingestor.archive.enrichment import ARM_ORDER, run_enrichment_attempt


def test_arm_order_is_locked() -> None:
    assert ARM_ORDER == ("markets", "receipt", "funding", "hydrate")


def test_full_attempt_records_status_for_every_arm() -> None:
    archive = ArchiveSettings(ARCHIVE_ENABLED=True, ARCHIVE_FEATURING_ENABLED=True)
    result = run_enrichment_attempt(archive=archive)
    assert set(result.statuses) == set(ARM_ORDER)
    assert all(status for status in result.statuses.values())
    assert result.enrichment_budget_version == archive.enrichment_budget_version


def test_reuse_records_prior_status_without_silent_null() -> None:
    archive = ArchiveSettings(ARCHIVE_ENABLED=True, ARCHIVE_FEATURING_ENABLED=True)
    result = run_enrichment_attempt(
        archive=archive,
        reuse={"receipt": "ok", "funding": "miss"},
    )
    assert result.statuses["receipt"] == "ok"
    assert result.statuses["funding"] == "miss"
    assert result.statuses["markets"] == "partial"
    assert result.statuses["hydrate"] == "pending"
