"""Featured enrichment diagnostic metrics and ready isolation."""

from __future__ import annotations

from polymarket_insider_tracker.ingestor.archive.enrichment_health import (
    EnrichmentHealthSignals,
)
from polymarket_insider_tracker.ingestor.archive.health import ArchiveHealthSignals
from polymarket_insider_tracker.ingestor.archive.signed_flow_kpi import (
    DisagreementClass,
    SignedFlowKpi,
)


def test_enrichment_degraded_does_not_change_tape_health() -> None:
    signals = EnrichmentHealthSignals()
    signals.record_loop_error(now=1_000.0)
    status = signals.evaluate(now=1_010.0)
    assert status.status == "degraded"
    assert ArchiveHealthSignals().evaluate(now=1_010.0).status == "up"


def test_enrichment_never_reports_down() -> None:
    signals = EnrichmentHealthSignals()
    signals.record_loop_error(now=50.0)
    for _ in range(10):
        signals.record_attempt(
            {"markets": "failed", "receipt": "skipped_budget"},
            now=55.0,
        )
    assert signals.evaluate(now=55.0).status == "degraded"


def test_skipped_budget_ratio_degrades() -> None:
    signals = EnrichmentHealthSignals()
    for offset in range(6):
        signals.record_attempt(
            {
                "markets": "ok",
                "receipt": "skipped_budget",
                "funding": "ok",
                "hydrate": "ok",
            },
            now=100.0 + offset,
        )
    status = signals.evaluate(now=110.0)
    assert status.status == "degraded"
    assert status.last_error is not None
    assert "skipped_budget_ratio" in status.last_error


def test_signed_flow_observe_and_publish_are_safe() -> None:
    kpi = SignedFlowKpi(publish_min_sample=1)
    kpi.observe(DisagreementClass.AGREE)
    assert kpi.publish() is True
    assert kpi.published is True
