"""λ/imbalance stay gated until KPI published for a classifiable cohort."""

from __future__ import annotations

from polymarket_insider_tracker.ingestor.archive.signed_flow_kpi import (
    DisagreementClass,
    SignedFlowKpi,
    lambda_core_allowed,
)


def test_lambda_core_requires_published_kpi() -> None:
    kpi = SignedFlowKpi(publish_min_sample=3)
    assert lambda_core_allowed(kpi_published=kpi.published) is False
    assert kpi.publish() is False
    assert kpi.published is False
    for _ in range(3):
        kpi.observe(DisagreementClass.AGREE)
    assert kpi.publish() is True
    assert lambda_core_allowed(kpi_published=kpi.published) is True


def test_unavailable_observations_do_not_count_toward_publish() -> None:
    kpi = SignedFlowKpi(publish_min_sample=2)
    kpi.observe(DisagreementClass.UNAVAILABLE)
    kpi.observe(DisagreementClass.UNAVAILABLE)
    assert kpi.can_publish() is False
    kpi.observe(DisagreementClass.AGREE)
    kpi.observe(DisagreementClass.COMPLEMENT)
    assert kpi.publish() is True
