"""In-process capacity signals: partition-miss and insert-rate metrics."""

from __future__ import annotations

from prometheus_client import REGISTRY
from sqlalchemy.exc import ProgrammingError

from polymarket_insider_tracker.ingestor.archive.metrics import (
    ARCHIVE_INSERT_RATE,
    ARCHIVE_PARTITION_MISS_TOTAL,
    PrometheusArchiveMetrics,
)
from polymarket_insider_tracker.ingestor.archive.writer import is_partition_miss


def _counter_value(name: str, **labels: str) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


def test_prometheus_metrics_record_insert_rate_and_partition_miss() -> None:
    metrics = PrometheusArchiveMetrics()
    before_inserts = _counter_value("polymarket_archive_insert_rate_total")
    before_miss = _counter_value("polymarket_archive_partition_miss_total")
    metrics.record_insert("inserted")
    metrics.record_insert("duplicate")
    metrics.record_insert("failed")
    metrics.record_partition_miss()
    assert _counter_value("polymarket_archive_insert_rate_total") == before_inserts + 2
    assert _counter_value("polymarket_archive_partition_miss_total") == before_miss + 1
    assert ARCHIVE_INSERT_RATE is not None
    assert ARCHIVE_PARTITION_MISS_TOTAL is not None


def test_partition_miss_detection() -> None:
    error = ProgrammingError("stmt", {}, Exception("no partition of relation trades found"))
    assert is_partition_miss(error) is True
    other = ProgrammingError("stmt", {}, Exception("permission denied"))
    assert is_partition_miss(other) is False
