"""Shared-arm reuse contract (status dict) for both-leg hybrid policy."""

from __future__ import annotations

from polymarket_insider_tracker.config import ArchiveSettings
from polymarket_insider_tracker.ingestor.archive.enrichment import run_enrichment_attempt


def test_shared_arm_reuse_avoids_double_status_rewrite() -> None:
    archive = ArchiveSettings(ARCHIVE_ENABLED=True, ARCHIVE_FEATURING_ENABLED=True)
    first = run_enrichment_attempt(archive=archive)
    second = run_enrichment_attempt(
        archive=archive,
        reuse={
            "receipt": first.statuses["receipt"],
            "funding": first.statuses["funding"],
            "hydrate": first.statuses["hydrate"],
        },
    )
    assert second.statuses["receipt"] == first.statuses["receipt"]
    assert second.statuses["funding"] == first.statuses["funding"]
    assert second.statuses["hydrate"] == first.statuses["hydrate"]
