"""Featuring gate evaluation and enrichment enqueue."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from polymarket_insider_tracker.config import ArchiveSettings
from polymarket_insider_tracker.ingestor.archive.knowability import KNOWABILITY_POLICY_VERSION
from polymarket_insider_tracker.ingestor.trade_rows import TradeObservation
from polymarket_insider_tracker.redaction import redact_exception_message
from polymarket_insider_tracker.storage.models import TradeModel
from polymarket_insider_tracker.storage.repos import (
    FeaturingEnrichmentRepository,
    MarketsRepository,
)

__all__ = [
    "FeaturingDecision",
    "cancel_featuring_background_tasks",
    "enqueue_hot_backfill_for_market",
    "evaluate_featuring",
    "hot_cutoff",
    "is_still_hot",
    "schedule_featuring_enqueue",
    "schedule_regime_upgrade_backfill",
    "should_run_featuring_workers",
    "tracked_featuring_task_count",
]

logger = logging.getLogger(__name__)

_BACKGROUND_TASKS: set[asyncio.Task[None]] = set()


class SessionFactory(Protocol):
    def get_async_session(self) -> AbstractAsyncContextManager[AsyncSession]: ...


REGIME_PRIVATE_EDGE = "private_edge_possible"
REGIME_PRIVATE_SETTLEMENT_LEGACY = "private_settlement_possible"
REGIME_PRIVATE_FACTOR_LEGACY = "private_factor_possible"
REGIME_UNKNOWN = "unknown"
REGIME_NO_PRIVATE_EDGE = "no_private_edge"
FEATURING_ELIGIBLE_REGIMES = frozenset(
    {
        REGIME_PRIVATE_EDGE,
        REGIME_PRIVATE_SETTLEMENT_LEGACY,
        REGIME_PRIVATE_FACTOR_LEGACY,
    }
)


@dataclass(frozen=True)
class FeaturingDecision:
    """Outcome of one featuring-gate evaluation."""

    eligible: bool
    reason: str
    featuring_config_version: str
    trigger: str


def should_run_featuring_workers(archive: ArchiveSettings) -> bool:
    return archive.featuring_effectively_enabled


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def hot_cutoff(*, now: datetime, hot_window_days: int) -> datetime:
    return _as_utc(now) - timedelta(days=hot_window_days)


def is_still_hot(*, trade_ts: datetime, now: datetime, hot_window_days: int) -> bool:
    return _as_utc(trade_ts) >= hot_cutoff(now=now, hot_window_days=hot_window_days)


def evaluate_featuring(
    *,
    archive: ArchiveSettings,
    regime: str | None,
    notional_usdc: Decimal | int | float,
    observation_id: str,
    trigger: str = "insert_time",
) -> FeaturingDecision:
    version = archive.featuring_config_version
    if not archive.featuring_effectively_enabled:
        return FeaturingDecision(False, "featuring_disabled", version, trigger)
    regime_reason = _regime_block_reason(regime, archive.featuring_unknown_opt_in)
    if regime_reason == "regime_no_private_edge":
        return _no_private_edge_path(archive, observation_id, version, trigger)
    if regime_reason is not None:
        return FeaturingDecision(False, regime_reason, version, trigger)
    if Decimal(str(notional_usdc)) < Decimal(archive.featuring_notional_cutoff_usdc):
        return FeaturingDecision(False, "below_notional", version, trigger)
    return FeaturingDecision(True, "eligible", version, trigger)


def _regime_block_reason(regime: str | None, unknown_opt_in: bool) -> str | None:
    if regime in FEATURING_ELIGIBLE_REGIMES:
        return None
    if regime == REGIME_UNKNOWN:
        return None if unknown_opt_in else "regime_unknown"
    if regime == REGIME_NO_PRIVATE_EDGE:
        return "regime_no_private_edge"
    return "regime_unknown"


def is_featuring_regime(regime: str | None) -> bool:
    return regime in FEATURING_ELIGIBLE_REGIMES


def _no_private_edge_path(
    archive: ArchiveSettings,
    observation_id: str,
    version: str,
    trigger: str,
) -> FeaturingDecision:
    if _classifier_control_hit(observation_id, archive.classifier_control_sample_rate):
        return FeaturingDecision(True, "classifier_control", version, "classifier_control")
    return FeaturingDecision(False, "regime_no_private_edge", version, trigger)


def _classifier_control_hit(observation_id: str, rate: float) -> bool:
    if rate <= 0:
        return False
    digest = hashlib.sha256(observation_id.encode("utf-8")).digest()
    bucket = int.from_bytes(digest[:8], "big") / float(2**64)
    return bucket < rate


def utc_now() -> datetime:
    return datetime.now(UTC)


def _record_enqueue_metric(eligible: bool, reason: str) -> None:
    from polymarket_insider_tracker.ingestor.archive.enrichment_health import (
        FEATURING_REASON_TOTAL,
        enrichment_health,
    )

    enrichment_health().record_enqueue(eligible=eligible)
    FEATURING_REASON_TOTAL.labels(reason=reason).inc()


def _record_enqueue_error() -> None:
    from polymarket_insider_tracker.ingestor.archive.enrichment_health import enrichment_health

    enrichment_health().record_enqueue_error()


async def enqueue_after_insert(
    db_manager: SessionFactory,
    *,
    observation: TradeObservation,
    archive: ArchiveSettings,
) -> FeaturingDecision | None:
    if not should_run_featuring_workers(archive):
        return None
    trade_ts = observation.event.timestamp
    notional = observation.event.price * observation.event.size
    async with db_manager.get_async_session() as session:
        regime = await _regime_at(session, observation.event.market_id, trade_ts)
        decision = evaluate_featuring(
            archive=archive,
            regime=regime,
            notional_usdc=notional,
            observation_id=observation.identity,
        )
        await _persist_decision(session, observation, archive, decision)
        await session.commit()
        _record_enqueue_metric(decision.eligible, decision.reason)
        return decision


async def _regime_at(session: AsyncSession, condition_id: str, trade_ts: datetime) -> str | None:
    # Only current policy vocabulary; legacy always_latent/windowed rows stay history.
    row = await MarketsRepository(session).latest_at_or_before(
        condition_id,
        trade_ts,
        policy_version=KNOWABILITY_POLICY_VERSION,
    )
    if row is None:
        return None
    return row.info_knowability_regime


async def _persist_decision(
    session: AsyncSession,
    observation: TradeObservation,
    archive: ArchiveSettings,
    decision: FeaturingDecision,
) -> None:
    repo = FeaturingEnrichmentRepository(session)
    trade = await _load_trade(session, observation)
    if trade is not None:
        trade.featuring_config_version = decision.featuring_config_version
        trade.featuring_reason = decision.reason
        trade.enrichment_budget_version = archive.enrichment_budget_version
    if not decision.eligible:
        return
    await repo.enqueue_work(
        observation_id=observation.identity,
        trade_ts=observation.event.timestamp,
        enrichment_budget_version=archive.enrichment_budget_version,
        trigger=decision.trigger,
        enqueued_at=utc_now(),
    )


async def _load_trade(session: AsyncSession, observation: TradeObservation) -> TradeModel | None:
    from sqlalchemy import select

    result = await session.execute(
        select(TradeModel)
        .where(TradeModel.observation_id == observation.identity)
        .where(TradeModel.trade_ts == observation.event.timestamp)
        .limit(1)
    )
    return result.scalar_one_or_none()


def schedule_featuring_enqueue(
    loop: asyncio.AbstractEventLoop,
    db_manager: SessionFactory,
    *,
    observation: TradeObservation,
    archive: ArchiveSettings,
) -> None:
    """Fire-and-forget featuring enqueue; never await on the insert hot path."""
    if not should_run_featuring_workers(archive):
        return
    _track_background(
        loop.create_task(
            _run_scheduled_enqueue(db_manager, observation=observation, archive=archive)
        )
    )


def tracked_featuring_task_count() -> int:
    return len(_BACKGROUND_TASKS)


async def cancel_featuring_background_tasks() -> None:
    """Cancel outstanding featuring enqueue/backfill tasks (shutdown)."""
    tasks = list(_BACKGROUND_TASKS)
    for task in tasks:
        task.cancel()
    for task in tasks:
        await _await_cancelled(task)


async def _await_cancelled(task: asyncio.Task[None]) -> None:
    try:
        await task
    except asyncio.CancelledError:
        return


def _track_background(task: asyncio.Task[None]) -> None:
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)


async def _run_scheduled_enqueue(
    db_manager: SessionFactory,
    *,
    observation: TradeObservation,
    archive: ArchiveSettings,
) -> None:
    try:
        await enqueue_after_insert(db_manager, observation=observation, archive=archive)
    except Exception as exc:
        logger.warning("featuring enqueue failed: %s", redact_exception_message(exc))
        _record_enqueue_error()


async def enqueue_hot_backfill_for_market(
    session: AsyncSession,
    *,
    condition_id: str,
    new_regime: str,
    archive: ArchiveSettings,
    now: datetime,
) -> int:
    """Enqueue featuring for hot notional-eligible fills after regime upgrade.

    Hot membership uses ``ARCHIVE_HOT_WINDOW_DAYS`` at enqueue decision time.
    """
    if not is_featuring_regime(new_regime):
        return 0
    if not should_run_featuring_workers(archive):
        return 0
    cutoff = hot_cutoff(now=now, hot_window_days=archive.hot_window_days)
    trades = await _hot_trades(session, condition_id=condition_id, cutoff=cutoff)
    enqueued = 0
    for trade in trades:
        enqueued += await _maybe_enqueue_backfill(session, trade, archive, now, regime=new_regime)
    return enqueued


async def _hot_trades(
    session: AsyncSession, *, condition_id: str, cutoff: datetime
) -> list[TradeModel]:
    from sqlalchemy import select

    result = await session.execute(
        select(TradeModel)
        .where(TradeModel.condition_id == condition_id)
        .where(TradeModel.trade_ts >= cutoff)
    )
    return list(result.scalars().all())


async def _maybe_enqueue_backfill(
    session: AsyncSession,
    trade: TradeModel,
    archive: ArchiveSettings,
    now: datetime,
    *,
    regime: str,
) -> int:
    decision = evaluate_featuring(
        archive=archive,
        regime=regime,
        notional_usdc=trade.notional_usdc,
        observation_id=trade.observation_id,
        trigger="regime_upgrade",
    )
    if not decision.eligible:
        return 0
    if not is_still_hot(trade_ts=trade.trade_ts, now=now, hot_window_days=archive.hot_window_days):
        return 0
    created = await FeaturingEnrichmentRepository(session).enqueue_work(
        observation_id=trade.observation_id,
        trade_ts=trade.trade_ts,
        enrichment_budget_version=archive.enrichment_budget_version,
        trigger="regime_upgrade",
        enqueued_at=now,
    )
    return 1 if created is not None else 0


def schedule_regime_upgrade_backfill(
    loop: asyncio.AbstractEventLoop,
    db_manager: SessionFactory,
    *,
    condition_id: str,
    new_regime: str,
    archive: ArchiveSettings,
) -> None:
    """Fire-and-forget hot backfill; never await on insert or knowability hot path."""
    if not should_run_featuring_workers(archive):
        return
    _track_background(
        loop.create_task(
            _run_regime_backfill(
                db_manager,
                condition_id=condition_id,
                new_regime=new_regime,
                archive=archive,
            )
        )
    )


async def _run_regime_backfill(
    db_manager: SessionFactory,
    *,
    condition_id: str,
    new_regime: str,
    archive: ArchiveSettings,
) -> None:
    try:
        async with db_manager.get_async_session() as session:
            await enqueue_hot_backfill_for_market(
                session,
                condition_id=condition_id,
                new_regime=new_regime,
                archive=archive,
                now=utc_now(),
            )
            await session.commit()
    except Exception as exc:
        logger.warning("regime upgrade backfill failed: %s", redact_exception_message(exc))
