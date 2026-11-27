"""Budget degrade-from-bottom; markets never skipped."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from polymarket_insider_tracker.config import ArchiveSettings
from polymarket_insider_tracker.ingestor.archive.enrichment import (
    BudgetLedger,
    run_enrichment_attempt,
)


def test_markets_never_skipped_for_budget_even_when_forced() -> None:
    archive = ArchiveSettings(ARCHIVE_ENABLED=True, ARCHIVE_FEATURING_ENABLED=True)
    result = run_enrichment_attempt(
        archive=archive,
        force_skip=frozenset({"markets", "hydrate"}),
    )
    assert result.statuses["markets"] == "failed"
    assert result.statuses["hydrate"] == "skipped_budget"


def test_degrade_skips_hydrate_then_funding_when_rpc_exhausted() -> None:
    archive = ArchiveSettings(
        ARCHIVE_ENABLED=True,
        ARCHIVE_FEATURING_ENABLED=True,
        ARCHIVE_ENRICHMENT_RPC_CAP=0,
    )
    ledger = BudgetLedger.from_settings(archive)
    result = run_enrichment_attempt(archive=archive, budget=ledger)
    assert result.statuses["markets"] == "partial"
    assert result.statuses["receipt"] == "skipped_budget"
    assert result.statuses["funding"] == "skipped_budget"
    assert result.statuses["hydrate"] in {"pending", "skipped_budget"}


def test_wall_clock_exhaustion_skips_degradable_arms() -> None:
    archive = ArchiveSettings(
        ARCHIVE_ENABLED=True,
        ARCHIVE_FEATURING_ENABLED=True,
        ARCHIVE_ENRICHMENT_WALL_SECONDS=1,
    )
    ledger = BudgetLedger.from_settings(archive)
    ledger.started_at = datetime.now(UTC) - timedelta(seconds=5)
    result = run_enrichment_attempt(archive=archive, budget=ledger)
    assert result.statuses["markets"] == "partial"
    assert result.statuses["receipt"] == "skipped_budget"
    assert result.statuses["funding"] == "skipped_budget"
    assert result.statuses["hydrate"] == "skipped_budget"
