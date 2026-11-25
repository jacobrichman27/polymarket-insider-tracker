"""Outcome-repair KPI signals (post-cutover population only)."""

from __future__ import annotations

from dataclasses import dataclass

from prometheus_client import Gauge

from polymarket_insider_tracker.ingestor.health import ComponentStatus

OUTCOME_REPAIR_LAG_BREACH = Gauge(
    "polymarket_outcome_repair_lag_breach",
    "1 when post-cutover thin not_attempted rows exceed lag ceiling",
)
OUTCOME_REPAIR_UNREPAIRED_RATIO = Gauge(
    "polymarket_outcome_repair_unrepaired_ratio",
    "Trailing unrepaired ratio among thin post-cutover rows",
)
OUTCOME_REPAIR_KPI_DEGRADED = Gauge(
    "polymarket_outcome_repair_kpi_degraded",
    "1 when repair KPI ceilings are breached",
)


@dataclass(frozen=True)
class RepairKpiSnapshot:
    thin_post_cutover: int
    not_attempted_past_lag: int
    unrepaired: int
    unrepaired_ratio: float
    lag_breach: bool
    unrepaired_breach: bool

    @property
    def degraded(self) -> bool:
        return self.lag_breach or self.unrepaired_breach


@dataclass
class OutcomeRepairHealthSignals:
    """Optional diagnostic; MUST NOT alone mark trade_archive down."""

    last_snapshot: RepairKpiSnapshot | None = None

    def update(self, snapshot: RepairKpiSnapshot) -> None:
        self.last_snapshot = snapshot
        OUTCOME_REPAIR_LAG_BREACH.set(1.0 if snapshot.lag_breach else 0.0)
        OUTCOME_REPAIR_UNREPAIRED_RATIO.set(snapshot.unrepaired_ratio)
        OUTCOME_REPAIR_KPI_DEGRADED.set(1.0 if snapshot.degraded else 0.0)

    def evaluate(self) -> ComponentStatus:
        snap = self.last_snapshot
        if snap is None or not snap.degraded:
            return ComponentStatus(status="up")
        reason = f"lag_breach={snap.lag_breach}; unrepaired_ratio={snap.unrepaired_ratio:.4f}"
        return ComponentStatus(status="degraded", last_error=reason)


def compute_kpi(
    *,
    thin_post_cutover: int,
    not_attempted_past_lag: int,
    unrepaired: int,
    unrepaired_max_ratio: float,
) -> RepairKpiSnapshot:
    ratio = 0.0 if thin_post_cutover <= 0 else unrepaired / thin_post_cutover
    return RepairKpiSnapshot(
        thin_post_cutover=thin_post_cutover,
        not_attempted_past_lag=not_attempted_past_lag,
        unrepaired=unrepaired,
        unrepaired_ratio=ratio,
        lag_breach=not_attempted_past_lag > 0,
        unrepaired_breach=ratio > unrepaired_max_ratio and thin_post_cutover > 0,
    )
