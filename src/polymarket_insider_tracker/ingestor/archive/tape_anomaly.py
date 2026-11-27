"""Insert-time tape anomaly counters for unexpected observation shapes."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from prometheus_client import Counter, Histogram

from polymarket_insider_tracker.ingestor.models import TradeEvent
from polymarket_insider_tracker.ingestor.trade_rows import TradeObservation

__all__ = ["anomaly_counts", "clear_anomaly_counts", "observe_tape_observation"]

TAPE_ANOMALY_TOTAL = Counter(
    "polymarket_tape_anomaly_total",
    "Unexpected observation shapes at archive insert time",
    ["kind"],
)
TAPE_INGEST_LAG_SECONDS = Histogram(
    "polymarket_tape_ingest_lag_seconds",
    "observed_at minus trade_ts at archive insert (seconds)",
    buckets=(0.0, 1.0, 5.0, 15.0, 60.0, 300.0, 900.0, 3600.0, 10_800.0),
)
TAPE_NOTIONAL_USDC = Histogram(
    "polymarket_tape_notional_usdc",
    "Trade notional (price * size) at archive insert",
    buckets=(1.0, 10.0, 100.0, 1_000.0, 5_000.0, 25_000.0, 100_000.0, 500_000.0),
)
TAPE_PRICE = Histogram(
    "polymarket_tape_price",
    "API price at archive insert",
    buckets=(0.0, 0.01, 0.05, 0.1, 0.25, 0.5, 0.75, 0.9, 0.95, 0.99, 1.0),
)

_FUTURE_SLACK_SECONDS = 120.0
_STALE_LAG_SECONDS = 3600.0
_PRICE_MIN = Decimal("0")
_PRICE_MAX = Decimal("1")

_ANOMALY_COUNTS: dict[str, int] = {}


def anomaly_counts() -> dict[str, int]:
    return dict(_ANOMALY_COUNTS)


def clear_anomaly_counts() -> None:
    _ANOMALY_COUNTS.clear()


def observe_tape_observation(
    observation: TradeObservation,
    *,
    raw_retention: bool,
    now: datetime | None = None,
) -> None:
    """Record distributions and anomaly kinds for one admitted observation."""
    stamp = now if now is not None else datetime.now(UTC)
    _record_distributions(observation, stamp)
    for kind in _anomaly_kinds(observation, raw_retention=raw_retention, now=stamp):
        _ANOMALY_COUNTS[kind] = _ANOMALY_COUNTS.get(kind, 0) + 1
        TAPE_ANOMALY_TOTAL.labels(kind=kind).inc()


def _record_distributions(observation: TradeObservation, now: datetime) -> None:
    event = observation.event
    lag = _lag_seconds(observation, now)
    if lag is not None:
        TAPE_INGEST_LAG_SECONDS.observe(max(0.0, lag))
    notional = float(event.price * event.size)
    if notional >= 0.0:
        TAPE_NOTIONAL_USDC.observe(notional)
    TAPE_PRICE.observe(float(event.price))


def _anomaly_kinds(
    observation: TradeObservation,
    *,
    raw_retention: bool,
    now: datetime,
) -> tuple[str, ...]:
    kinds: list[str] = []
    kinds.extend(_shape_kinds(observation))
    kinds.extend(_time_kinds(observation, now=now))
    kinds.extend(_raw_kinds(observation, raw_retention=raw_retention))
    return tuple(kinds)


def _shape_kinds(observation: TradeObservation) -> tuple[str, ...]:
    event = observation.event
    kinds = list(_outcome_price_side_kinds(event))
    kinds.extend(_size_identity_kinds(event))
    return tuple(kinds)


def _outcome_price_side_kinds(event: TradeEvent) -> tuple[str, ...]:
    kinds: list[str] = []
    if _thin_outcome(event.outcome, event.outcome_index):
        kinds.append("thin_outcome")
    kinds.extend(_price_side_kinds(event))
    return tuple(kinds)


def _price_side_kinds(event: TradeEvent) -> tuple[str, ...]:
    kinds: list[str] = []
    if event.price < _PRICE_MIN or event.price > _PRICE_MAX:
        kinds.append("price_out_of_range")
    if event.side.upper() not in {"BUY", "SELL"}:
        kinds.append("unexpected_side")
    return tuple(kinds)


def _size_identity_kinds(event: TradeEvent) -> tuple[str, ...]:
    kinds: list[str] = []
    if event.size <= 0 or (event.price * event.size) <= 0:
        kinds.append("nonpositive_size_or_notional")
    if not event.trade_id or not event.wallet_address:
        kinds.append("missing_identity_fields")
    return tuple(kinds)


def _time_kinds(observation: TradeObservation, *, now: datetime) -> tuple[str, ...]:
    trade_ts = observation.event.timestamp
    if trade_ts.tzinfo is None:
        return ("naive_trade_ts",)
    lag = (now - trade_ts).total_seconds()
    kinds: list[str] = []
    if lag < -_FUTURE_SLACK_SECONDS:
        kinds.append("future_trade_ts")
    if lag > _STALE_LAG_SECONDS:
        kinds.append("stale_trade_ts")
    return tuple(kinds)


def _raw_kinds(observation: TradeObservation, *, raw_retention: bool) -> tuple[str, ...]:
    if not raw_retention:
        return ()
    if observation.raw_row is None:
        return ("missing_raw_row",)
    return ()


def _thin_outcome(outcome: str | None, outcome_index: int | None) -> bool:
    if outcome_index == 999:
        return True
    return outcome is None or outcome == ""


def _lag_seconds(observation: TradeObservation, now: datetime) -> float | None:
    trade_ts = observation.event.timestamp
    if trade_ts.tzinfo is None:
        return None
    observed = observation.observed_at if observation.observed_at is not None else now
    if observed.tzinfo is None:
        return None
    return (observed - trade_ts).total_seconds()
