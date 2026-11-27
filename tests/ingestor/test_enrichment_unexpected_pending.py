"""Completed attempt honesty counters for stub/pending outcomes."""

from __future__ import annotations

from polymarket_insider_tracker.ingestor.archive.enrichment_health import EnrichmentHealthSignals


def test_receipt_pending_counts_as_unexpected() -> None:
    signals = EnrichmentHealthSignals()
    signals.record_attempt(
        {
            "markets": "partial",
            "receipt": "pending",
            "funding": "pending",
            "hydrate": "pending",
        },
        now=1_000.0,
    )
    assert signals.unexpected_counts.get("receipt_still_pending", 0) == 1


def test_hydrate_ok_counts_as_unverified_until_real_walk() -> None:
    signals = EnrichmentHealthSignals()
    signals.record_attempt(
        {
            "markets": "partial",
            "receipt": "ok",
            "funding": "pending",
            "hydrate": "ok",
        },
        now=1_001.0,
    )
    assert signals.unexpected_counts.get("hydrate_ok_unverified", 0) == 1
