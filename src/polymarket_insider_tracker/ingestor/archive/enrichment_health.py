"""Featured-enrichment diagnostic health and Prometheus metrics.

MUST NOT alone mark ``trade_archive`` down or fail ``/ready``.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from prometheus_client import Counter, Gauge

from polymarket_insider_tracker.ingestor.health import ComponentStatus

__all__ = [
    "EnrichmentHealthSignals",
    "enrichment_health",
    "record_arm_statuses",
    "record_disagreement",
    "set_signed_flow_published",
]

ENRICHMENT_ATTEMPTS_TOTAL = Counter(
    "polymarket_enrichment_attempts_total",
    "Featured enrichment attempts by result",
    ["result"],
)
ENRICHMENT_ARM_STATUS_TOTAL = Counter(
    "polymarket_enrichment_arm_status_total",
    "Per-arm status outcomes for featured enrichment",
    ["arm", "status"],
)
ENRICHMENT_LOOP_ERRORS_TOTAL = Counter(
    "polymarket_enrichment_loop_errors_total",
    "Unhandled enrichment worker loop errors",
)
FEATURING_ENQUEUE_TOTAL = Counter(
    "polymarket_featuring_enqueue_total",
    "Featuring decisions / enqueue outcomes",
    ["result"],
)
FEATURING_REASON_TOTAL = Counter(
    "polymarket_featuring_reason_total",
    "Featuring gate reason codes (eligibility mix / unexpected shifts)",
    ["reason"],
)
SIGNED_FLOW_DISAGREEMENT_TOTAL = Counter(
    "polymarket_signed_flow_disagreement_total",
    "Signed-flow disagreement class observations",
    ["klass"],
)
SIGNED_FLOW_KPI_PUBLISHED = Gauge(
    "polymarket_signed_flow_kpi_published",
    "1 when signed-flow disagreement KPI is marked published",
)
ENRICHMENT_HEALTH_DEGRADED = Gauge(
    "polymarket_enrichment_health_degraded",
    "1 when featured_enrichment diagnostic is degraded",
)
ENRICHMENT_UNEXPECTED_TOTAL = Counter(
    "polymarket_enrichment_unexpected_total",
    "Enrichment outcomes that look incomplete or dishonest for claimed statuses",
    ["kind"],
)

_ERROR_WINDOW_SECONDS = 60.0
_SKIP_BUDGET_RATIO = 0.5
_MARKETS_FAIL_RATIO = 0.2
_RECENT_ATTEMPT_CAP = 40


@dataclass
class EnrichmentHealthSignals:
    """Optional diagnostic; never reports ``down`` (ready isolation)."""

    recent_loop_error_at: float | None = None
    recent_enqueue_error_at: float | None = None
    attempt_count: int = 0
    enqueue_error_count: int = 0
    unexpected_counts: dict[str, int] = field(default_factory=dict[str, int])
    _attempt_flags: list[tuple[float, bool, bool]] = field(default_factory=list)
    # (stamp, markets_failed, any_skipped_budget)

    def record_loop_error(self, *, now: float | None = None) -> None:
        stamp = _now(now)
        self.recent_loop_error_at = stamp
        ENRICHMENT_LOOP_ERRORS_TOTAL.inc()
        ENRICHMENT_ATTEMPTS_TOTAL.labels(result="loop_error").inc()

    def record_enqueue(self, *, eligible: bool) -> None:
        label = "enqueued" if eligible else "rejected"
        FEATURING_ENQUEUE_TOTAL.labels(result=label).inc()

    def record_enqueue_error(self, *, now: float | None = None) -> None:
        self.recent_enqueue_error_at = _now(now)
        self.enqueue_error_count += 1
        FEATURING_ENQUEUE_TOTAL.labels(result="error").inc()

    def record_attempt(self, statuses: dict[str, str], *, now: float | None = None) -> None:
        stamp = _now(now)
        record_arm_statuses(statuses)
        if not statuses:
            ENRICHMENT_ATTEMPTS_TOTAL.labels(result="trade_missing").inc()
            return
        self.attempt_count += 1
        ENRICHMENT_ATTEMPTS_TOTAL.labels(result="completed").inc()
        self._note_unexpected(statuses)
        markets_failed = statuses.get("markets") == "failed"
        skipped = any(status == "skipped_budget" for status in statuses.values())
        self._attempt_flags.append((stamp, markets_failed, skipped))
        self._prune(stamp)

    def _note_unexpected(self, statuses: dict[str, str]) -> None:
        for kind in _unexpected_kinds(statuses):
            self.unexpected_counts[kind] = self.unexpected_counts.get(kind, 0) + 1
            ENRICHMENT_UNEXPECTED_TOTAL.labels(kind=kind).inc()

    def evaluate(self, *, now: float | None = None) -> ComponentStatus:
        stamp = _now(now)
        self._prune(stamp)
        reason = self._degraded_reason(stamp)
        ENRICHMENT_HEALTH_DEGRADED.set(0.0 if reason is None else 1.0)
        if reason is None:
            return ComponentStatus(status="up")
        return ComponentStatus(status="degraded", last_error=reason)

    def _degraded_reason(self, now: float) -> str | None:
        if self._fresh_error(self.recent_loop_error_at, now):
            return "enrichment_loop_error"
        if self._fresh_error(self.recent_enqueue_error_at, now):
            return "featuring_enqueue_error"
        return self._ratio_reason()

    def _ratio_reason(self) -> str | None:
        if not self._attempt_flags:
            return None
        total = len(self._attempt_flags)
        return _ratio_breach(self._attempt_flags, total)

    def _fresh_error(self, at: float | None, now: float) -> bool:
        if at is None:
            return False
        return (now - at) <= _ERROR_WINDOW_SECONDS

    def _prune(self, now: float) -> None:
        cutoff = now - _ERROR_WINDOW_SECONDS
        kept = [row for row in self._attempt_flags if row[0] >= cutoff]
        self._attempt_flags = kept[-_RECENT_ATTEMPT_CAP:]


def _ratio_breach(flags: list[tuple[float, bool, bool]], total: int) -> str | None:
    markets = _count_flag(flags, index=1)
    if markets / total > _MARKETS_FAIL_RATIO:
        return f"markets_failed_ratio={markets}/{total}"
    skipped = _count_flag(flags, index=2)
    if skipped / total > _SKIP_BUDGET_RATIO:
        return f"skipped_budget_ratio={skipped}/{total}"
    return None


def _count_flag(flags: list[tuple[float, bool, bool]], *, index: int) -> int:
    return sum(1 for row in flags if row[index])


def record_arm_statuses(statuses: dict[str, str]) -> None:
    for arm, status in statuses.items():
        ENRICHMENT_ARM_STATUS_TOTAL.labels(arm=arm, status=status).inc()


def _unexpected_kinds(statuses: dict[str, str]) -> list[str]:
    kinds: list[str] = []
    if statuses.get("receipt") == "pending":
        kinds.append("receipt_still_pending")
    if statuses.get("hydrate") == "ok":
        kinds.append("hydrate_ok_unverified")
    allowed = {None, "ok", "partial", "failed", "pending", "skipped_budget", "miss"}
    if statuses.get("markets") not in allowed:
        kinds.append("markets_unknown_status")
    return kinds


def record_disagreement(klass: str) -> None:
    SIGNED_FLOW_DISAGREEMENT_TOTAL.labels(klass=klass).inc()


def set_signed_flow_published(published: bool) -> None:
    SIGNED_FLOW_KPI_PUBLISHED.set(1.0 if published else 0.0)


def _now(now: float | None) -> float:
    return time.time() if now is None else now


_PROCESS_SIGNALS = EnrichmentHealthSignals()


def enrichment_health() -> EnrichmentHealthSignals:
    """Process-wide diagnostic signals (shared by workers + /health)."""
    return _PROCESS_SIGNALS
