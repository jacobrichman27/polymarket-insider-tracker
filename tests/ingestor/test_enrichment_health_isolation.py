"""Enrichment lag / diagnostic must not alone mark trade_archive down."""

from __future__ import annotations

from polymarket_insider_tracker.ingestor.archive.enrichment_health import EnrichmentHealthSignals
from polymarket_insider_tracker.ingestor.archive.health import ArchiveHealthSignals
from polymarket_insider_tracker.ingestor.archive.signed_flow_kpi import (
    DisagreementClass,
    SignedFlowKpi,
)


def test_enrichment_kpi_does_not_change_tape_health() -> None:
    signals = ArchiveHealthSignals()
    kpi = SignedFlowKpi(publish_min_sample=1)
    kpi.observe(DisagreementClass.AGREE)
    assert kpi.publish() is True
    status = signals.evaluate(now=1_000.0)
    assert status.status == "up"


def test_featured_enrichment_degraded_leaves_tape_up() -> None:
    enrichment = EnrichmentHealthSignals()
    enrichment.record_enqueue_error(now=500.0)
    assert enrichment.evaluate(now=510.0).status == "degraded"
    assert ArchiveHealthSignals().evaluate(now=510.0).status == "up"
