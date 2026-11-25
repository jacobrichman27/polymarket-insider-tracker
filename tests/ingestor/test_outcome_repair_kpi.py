"""Repair KPI computation (US2)."""

from __future__ import annotations

from polymarket_insider_tracker.ingestor.archive.repair_kpi import compute_kpi


def test_kpi_lag_and_unrepaired_breaches() -> None:
    snap = compute_kpi(
        thin_post_cutover=100,
        not_attempted_past_lag=1,
        unrepaired=6,
        unrepaired_max_ratio=0.05,
    )
    assert snap.lag_breach is True
    assert snap.unrepaired_breach is True
    assert snap.degraded is True
    assert snap.unrepaired_ratio == 0.06


def test_kpi_pre_cutover_excluded_when_thin_zero() -> None:
    snap = compute_kpi(
        thin_post_cutover=0,
        not_attempted_past_lag=0,
        unrepaired=0,
        unrepaired_max_ratio=0.05,
    )
    assert snap.degraded is False
