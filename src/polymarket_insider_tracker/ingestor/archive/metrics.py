"""Prometheus metrics for the research trade archive (Phase A0)."""

from __future__ import annotations

from prometheus_client import Counter, Gauge

ARCHIVE_INSERTS_TOTAL = Counter(
    "polymarket_archive_inserts_total",
    "Archive tape insert attempts by result",
    ["result"],
)
ARCHIVE_OWED_OBSERVATIONS = Gauge(
    "polymarket_archive_owed_observations",
    "Currently owed archive-destined observations",
)
ARCHIVE_WRITE_FAILURES_TOTAL = Counter(
    "polymarket_archive_write_failures_total",
    "Archive write failures by reason",
    ["reason"],
)
ARCHIVE_OLDEST_OWED_AGE_SECONDS = Gauge(
    "polymarket_archive_oldest_owed_age_seconds",
    "Age in seconds of the oldest owed archive observation",
)
ARCHIVE_INSERT_RATE = Counter(
    "polymarket_archive_insert_rate_total",
    "Successful archive inserts (for sizing / 2x rate alarms)",
)
ARCHIVE_PARTITION_MISS_TOTAL = Counter(
    "polymarket_archive_partition_miss_total",
    "Archive inserts that failed closed on a missing partition",
)


class PrometheusArchiveMetrics:
    def record_insert(self, result: str) -> None:
        ARCHIVE_INSERTS_TOTAL.labels(result=result).inc()
        if result in {"inserted", "duplicate"}:
            ARCHIVE_INSERT_RATE.inc()

    def record_partition_miss(self) -> None:
        ARCHIVE_PARTITION_MISS_TOTAL.inc()

    def record_write_failure(self, reason: str) -> None:
        ARCHIVE_WRITE_FAILURES_TOTAL.labels(reason=reason).inc()

    def set_owed(self, count: int, oldest_age_seconds: float) -> None:
        ARCHIVE_OWED_OBSERVATIONS.set(count)
        ARCHIVE_OLDEST_OWED_AGE_SECONDS.set(oldest_age_seconds)
