"""Repair KPI degraded must not alone mark trade_archive down / ready fail."""

from __future__ import annotations

from polymarket_insider_tracker.ingestor.archive.health import ArchiveHealthSignals
from polymarket_insider_tracker.ingestor.archive.repair_kpi import (
    OutcomeRepairHealthSignals,
    compute_kpi,
)
from polymarket_insider_tracker.ingestor.health import HealthMonitor


def test_repair_degraded_does_not_fail_readiness() -> None:
    repair = OutcomeRepairHealthSignals()
    repair.update(
        compute_kpi(
            thin_post_cutover=20,
            not_attempted_past_lag=2,
            unrepaired=2,
            unrepaired_max_ratio=0.05,
        )
    )
    tape = ArchiveHealthSignals().evaluate(0.0)
    components = {
        "trade_archive": tape,
        "outcome_repair": repair.evaluate(),
    }
    assert components["outcome_repair"].status == "degraded"
    assert components["trade_archive"].status == "up"
    assert HealthMonitor.all_components_up(components) is True
