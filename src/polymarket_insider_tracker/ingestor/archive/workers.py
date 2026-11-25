"""Background markets / repair / knowability workers (non-blocking)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol, cast

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from polymarket_insider_tracker.config import ArchiveSettings
from polymarket_insider_tracker.ingestor.archive.decisions_client import (
    BudgetGate,
    HttpxDecisionsClient,
    NullDecisionsClient,
)
from polymarket_insider_tracker.ingestor.archive.knowability import classify_market
from polymarket_insider_tracker.ingestor.archive.markets import (
    append_market_version,
    parse_token_outcomes,
)
from polymarket_insider_tracker.ingestor.archive.outcome_repair import repair_trade_row
from polymarket_insider_tracker.ingestor.archive.repair_kpi import (
    OutcomeRepairHealthSignals,
    compute_kpi,
)
from polymarket_insider_tracker.ingestor.archive.state import ensure_repair_cutover
from polymarket_insider_tracker.ingestor.gamma_client import DEFAULT_HOST
from polymarket_insider_tracker.redaction import redact_exception_message
from polymarket_insider_tracker.storage.models import TradeModel
from polymarket_insider_tracker.storage.repos import MarketsRepository, TradeArchiveRepository

logger = logging.getLogger(__name__)

GammaFetch = Callable[[str], Awaitable[dict[str, Any] | None]]


class SessionFactory(Protocol):
    def get_async_session(self) -> AbstractAsyncContextManager[AsyncSession]: ...


@dataclass
class MarketWarmCoordinator:
    """Process-scoped Decisions budget + market-grain warm dedupe (never per fill)."""

    budget: BudgetGate
    _in_flight: set[str] = field(default_factory=lambda: set[str]())
    _done: set[str] = field(default_factory=lambda: set[str]())

    def try_begin(self, condition_id: str) -> bool:
        if condition_id in self._done or condition_id in self._in_flight:
            return False
        self._in_flight.add(condition_id)
        return True

    def finish(self, condition_id: str, *, kept: bool) -> None:
        self._in_flight.discard(condition_id)
        if kept:
            self._done.add(condition_id)


@dataclass
class ArchiveWorkerHandles:
    repair_task: asyncio.Task[None] | None = None
    stop_event: asyncio.Event | None = None
    warm: MarketWarmCoordinator | None = None


def build_warm_coordinator(archive: ArchiveSettings) -> MarketWarmCoordinator:
    return MarketWarmCoordinator(
        budget=BudgetGate(max_calls_per_day=archive.knowability_model_max_calls_per_day)
    )


async def fetch_gamma_market(condition_id: str) -> dict[str, Any] | None:
    url = f"{DEFAULT_HOST}/markets"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, params={"condition_ids": condition_id})
            response.raise_for_status()
            body = response.json()
    except (httpx.HTTPError, ValueError, TypeError) as exc:
        logger.warning("gamma market fetch failed: %s", redact_exception_message(exc))
        return None
    return first_market(body)


def first_market(body: object) -> dict[str, Any] | None:
    """Gamma ``GET /markets?condition_ids=…`` returns a JSON array of markets."""
    if not isinstance(body, list) or not body:
        return None
    first_obj = cast(object, body[0])
    if isinstance(first_obj, dict):
        return cast(dict[str, Any], first_obj)
    return None


async def _has_market_version(db_manager: SessionFactory, condition_id: str) -> bool:
    async with db_manager.get_async_session() as session:
        row = await MarketsRepository(session).latest(condition_id)
        return row is not None


async def _persist_warm(
    db_manager: SessionFactory,
    *,
    condition_id: str,
    raw: dict[str, Any],
    outcomes: dict[str, Any],
    archive: ArchiveSettings,
    coordinator: MarketWarmCoordinator,
) -> None:
    question = _str_field(raw, "question")
    series_slug = _str_field(raw, "seriesSlug") or _str_field(raw, "series_slug")
    category = _str_field(raw, "category")
    decisions = _decisions_client(archive, budget=coordinator.budget)
    budget = decisions.budget if isinstance(decisions, HttpxDecisionsClient) else None
    async with db_manager.get_async_session() as session:
        classification = await classify_market(
            session,
            question=question,
            series_slug=series_slug,
            category=category,
            market_json=raw,
            decisions=decisions,
            model_enabled=archive.knowability_model_effectively_enabled,
            budget=budget,
        )
        await append_market_version(
            session,
            condition_id=condition_id,
            token_outcomes=outcomes,
            question=question,
            series_slug=series_slug,
            info_knowability_regime=classification.regime,
            knowable_from=classification.knowable_from,
            knowability_label_source=classification.label_source,
            knowability_policy_version=classification.policy_version,
            source_version="gamma",
            raw_market_json=raw,
        )
        await session.commit()


async def _fetch_warm_gamma(
    condition_id: str, fetcher: GammaFetch
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    raw = await fetcher(condition_id)
    if raw is None:
        return None
    outcomes = parse_token_outcomes(raw)
    if not outcomes:
        return None
    return raw, outcomes


async def warm_market_metadata(
    db_manager: SessionFactory,
    *,
    condition_id: str,
    archive: ArchiveSettings,
    coordinator: MarketWarmCoordinator | None = None,
    fetch_market: GammaFetch | None = None,
) -> bool:
    """Fetch Gamma metadata once per market. Returns True when the market is warmed."""
    if not archive.enabled:
        return False
    if await _has_market_version(db_manager, condition_id):
        return True
    warm = coordinator if coordinator is not None else build_warm_coordinator(archive)
    payload = await _fetch_warm_gamma(condition_id, fetch_market or fetch_gamma_market)
    if payload is None:
        return False
    raw, outcomes = payload
    try:
        await _persist_warm(
            db_manager,
            condition_id=condition_id,
            raw=raw,
            outcomes=outcomes,
            archive=archive,
            coordinator=warm,
        )
    except Exception as exc:
        logger.warning("markets warm failed: %s", redact_exception_message(exc))
        return False
    return True


async def _run_scheduled_warm(
    db_manager: SessionFactory,
    *,
    condition_id: str,
    archive: ArchiveSettings,
    coordinator: MarketWarmCoordinator,
    fetch_market: GammaFetch | None,
) -> None:
    kept = False
    try:
        kept = await warm_market_metadata(
            db_manager,
            condition_id=condition_id,
            archive=archive,
            coordinator=coordinator,
            fetch_market=fetch_market,
        )
    finally:
        coordinator.finish(condition_id, kept=kept)


def schedule_market_warm(
    loop: asyncio.AbstractEventLoop,
    db_manager: SessionFactory,
    *,
    condition_id: str,
    archive: ArchiveSettings,
    coordinator: MarketWarmCoordinator | None = None,
    fetch_market: GammaFetch | None = None,
) -> None:
    """Fire-and-forget warm at market grain; never awaited on the insert hot path."""
    if not archive.enabled:
        return
    warm = coordinator if coordinator is not None else build_warm_coordinator(archive)
    if not warm.try_begin(condition_id):
        return
    loop.create_task(
        _run_scheduled_warm(
            db_manager,
            condition_id=condition_id,
            archive=archive,
            coordinator=warm,
            fetch_market=fetch_market,
        )
    )


def _decisions_client(
    archive: ArchiveSettings, *, budget: BudgetGate
) -> HttpxDecisionsClient | NullDecisionsClient:
    if not archive.knowability_model_effectively_enabled:
        return NullDecisionsClient()
    key = archive.knowability_model_api_key
    assert key is not None
    return HttpxDecisionsClient(
        api_key=key.get_secret_value(),
        budget=budget,
    )


def _str_field(raw: dict[str, Any], name: str) -> str | None:
    value = raw.get(name)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


async def ensure_cutover_if_repair_on(
    db_manager: SessionFactory, *, source_id: str, archive: ArchiveSettings
) -> datetime | None:
    if not archive.outcome_repair_effectively_enabled:
        return None
    async with db_manager.get_async_session() as session:
        state = await ensure_repair_cutover(session, source_id=source_id)
        await session.commit()
        return state.repair_enabled_at


async def refresh_repair_kpi(
    db_manager: SessionFactory,
    *,
    source_id: str,
    archive: ArchiveSettings,
    health: OutcomeRepairHealthSignals,
    now: datetime | None = None,
) -> None:
    """Load thin post-cutover counts and publish lag / unrepaired KPI signals."""
    if not archive.outcome_repair_effectively_enabled:
        return
    stamp = now if now is not None else datetime.now(UTC)
    async with db_manager.get_async_session() as session:
        state = await TradeArchiveRepository(session).get_collector_state(source_id)
        if state is None or state.repair_enabled_at is None:
            return
        counts = await TradeArchiveRepository(session).count_outcome_repair_kpi(
            cutover=state.repair_enabled_at,
            now=stamp,
            lag_seconds=archive.outcome_repair_lag_seconds,
        )
    health.update(
        compute_kpi(
            thin_post_cutover=counts.thin_post_cutover,
            not_attempted_past_lag=counts.not_attempted_past_lag,
            unrepaired=counts.unrepaired,
            unrepaired_max_ratio=archive.outcome_repair_unrepaired_max_ratio,
        )
    )


async def run_repair_pass(
    db_manager: SessionFactory,
    *,
    source_id: str,
    archive: ArchiveSettings,
    health: OutcomeRepairHealthSignals | None = None,
    limit: int = 50,
) -> int:
    """Repair a batch of post-cutover not_attempted rows. Returns count attempted."""
    if not archive.outcome_repair_effectively_enabled:
        return 0
    cutover = await ensure_cutover_if_repair_on(db_manager, source_id=source_id, archive=archive)
    if cutover is None:
        return 0
    rows = await _load_pending_repairs(db_manager, cutover=cutover, limit=limit)
    for row in rows:
        await _repair_one(db_manager, row=row, cutover=cutover)
    if health is not None:
        await refresh_repair_kpi(db_manager, source_id=source_id, archive=archive, health=health)
    return len(rows)


async def _load_pending_repairs(
    db_manager: SessionFactory, *, cutover: datetime, limit: int
) -> list[TradeModel]:
    async with db_manager.get_async_session() as session:
        result = await session.execute(
            select(TradeModel)
            .where(TradeModel.observed_at >= cutover)
            .where(TradeModel.outcome_repair_status == "not_attempted")
            .order_by(TradeModel.observed_at.asc())
            .limit(limit)
        )
        return list(result.scalars().all())


async def _repair_one(db_manager: SessionFactory, *, row: TradeModel, cutover: datetime) -> None:
    try:
        async with db_manager.get_async_session() as session:
            await repair_trade_row(
                session,
                trade_ts=row.trade_ts,
                observation_id=row.observation_id,
                observed_at=row.observed_at,
                condition_id=row.condition_id,
                token_id=row.token_id,
                outcome=row.outcome,
                outcome_index=row.outcome_index,
                repair_enabled_at=cutover,
            )
            await session.commit()
    except Exception as exc:
        logger.warning("outcome repair failed: %s", redact_exception_message(exc))


async def repair_loop(
    db_manager: SessionFactory,
    *,
    source_id: str,
    archive: ArchiveSettings,
    stop_event: asyncio.Event,
    health: OutcomeRepairHealthSignals,
    interval_seconds: float = 5.0,
) -> None:
    while not stop_event.is_set():
        try:
            await run_repair_pass(db_manager, source_id=source_id, archive=archive, health=health)
        except Exception as exc:
            logger.warning("repair loop error: %s", redact_exception_message(exc))
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except TimeoutError:
            continue


def start_archive_workers(
    db_manager: SessionFactory,
    *,
    source_id: str,
    archive: ArchiveSettings,
    warm: MarketWarmCoordinator | None = None,
    repair_health: OutcomeRepairHealthSignals | None = None,
) -> ArchiveWorkerHandles:
    coord = warm if warm is not None else build_warm_coordinator(archive)
    handles = ArchiveWorkerHandles(stop_event=asyncio.Event(), warm=coord)
    if not archive.outcome_repair_effectively_enabled:
        return handles
    health = repair_health if repair_health is not None else OutcomeRepairHealthSignals()
    assert handles.stop_event is not None
    handles.repair_task = asyncio.create_task(
        repair_loop(
            db_manager,
            source_id=source_id,
            archive=archive,
            stop_event=handles.stop_event,
            health=health,
        )
    )
    return handles


async def stop_archive_workers(handles: ArchiveWorkerHandles) -> None:
    if handles.stop_event is not None:
        handles.stop_event.set()
    if handles.repair_task is None:
        return
    handles.repair_task.cancel()
    try:
        await handles.repair_task
    except asyncio.CancelledError:
        return
