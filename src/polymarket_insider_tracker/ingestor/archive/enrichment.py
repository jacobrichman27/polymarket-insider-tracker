"""Budgeted enrichment arm orchestration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from polymarket_insider_tracker.config import ArchiveSettings
from polymarket_insider_tracker.storage.models import EnrichmentWorkItemModel, TradeModel
from polymarket_insider_tracker.storage.repos import FeaturingEnrichmentRepository

__all__ = [
    "ARM_ORDER",
    "ArmContext",
    "ArmRunner",
    "BudgetLedger",
    "EnrichmentAttemptResult",
    "enrich_work_item",
    "run_enrichment_attempt",
]

# Orchestration key "markets" persists to trades.gamma_enrichment_status.
ARM_ORDER = ("markets", "receipt", "funding", "hydrate")
DEGRADE_ARMS = frozenset({"hydrate", "funding", "receipt"})
RPC_ARMS = frozenset({"receipt", "funding"})

ArmRunner = Callable[["ArmContext"], Awaitable[str]]


@dataclass
class BudgetLedger:
    """Tracks provisional wall / RPC / hydrate spend for one attempt."""

    wall_seconds: int
    rpc_cap: int
    hydrate_pages: int
    hydrate_seconds: int
    rpc_used: int = 0
    hydrate_pages_used: int = 0
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def from_settings(cls, archive: ArchiveSettings) -> BudgetLedger:
        return cls(
            wall_seconds=archive.enrichment_wall_seconds,
            rpc_cap=archive.enrichment_rpc_cap,
            hydrate_pages=archive.enrichment_hydrate_pages,
            hydrate_seconds=archive.enrichment_hydrate_seconds,
        )

    def wall_exhausted(self, *, now: datetime | None = None) -> bool:
        current = now if now is not None else datetime.now(UTC)
        elapsed = (current - self.started_at).total_seconds()
        return elapsed >= self.wall_seconds

    def can_spend_rpc(self, count: int = 1) -> bool:
        return self.rpc_used + count <= self.rpc_cap

    def spend_rpc(self, count: int = 1) -> None:
        self.rpc_used += count

    def can_spend_hydrate_page(self) -> bool:
        return self.hydrate_pages_used < self.hydrate_pages

    def hydrate_time_exhausted(self, *, now: datetime | None = None) -> bool:
        current = now if now is not None else datetime.now(UTC)
        elapsed = (current - self.started_at).total_seconds()
        return elapsed >= self.hydrate_seconds


@dataclass
class ArmContext:
    """Shared context for one featured enrichment attempt."""

    session: AsyncSession
    trade: TradeModel
    archive: ArchiveSettings
    ledger: BudgetLedger


@dataclass(frozen=True)
class EnrichmentAttemptResult:
    """Per-arm statuses for one featured enrichment attempt."""

    statuses: dict[str, str]
    enrichment_budget_version: str
    trade_missing: bool = False


def run_enrichment_attempt(
    *,
    archive: ArchiveSettings,
    reuse: dict[str, str] | None = None,
    force_skip: frozenset[str] | None = None,
    budget: BudgetLedger | None = None,
) -> EnrichmentAttemptResult:
    """Synchronous status planning helper (tests / degrade rules)."""
    ledger = budget if budget is not None else BudgetLedger.from_settings(archive)
    prior: dict[str, str] = {} if reuse is None else reuse
    skip: frozenset[str] = frozenset() if force_skip is None else force_skip
    statuses = {arm: _simulate_arm(arm, prior=prior, skip=skip, ledger=ledger) for arm in ARM_ORDER}
    return EnrichmentAttemptResult(
        statuses=statuses,
        enrichment_budget_version=archive.enrichment_budget_version,
    )


async def enrich_work_item(
    session: AsyncSession,
    work: EnrichmentWorkItemModel,
    *,
    archive: ArchiveSettings,
    runners: dict[str, ArmRunner],
) -> EnrichmentAttemptResult:
    """Claimed work: run arms in order and persist per-arm statuses."""
    from polymarket_insider_tracker.ingestor.archive.shared_arms import (
        apply_tape_pair_assist,
        load_shared_arm_reuse,
    )

    trade = await _load_trade(session, work.observation_id, work.trade_ts)
    if trade is None:
        return EnrichmentAttemptResult(
            {},
            archive.enrichment_budget_version,
            trade_missing=True,
        )
    ledger = BudgetLedger.from_settings(archive)
    context = ArmContext(session=session, trade=trade, archive=archive, ledger=ledger)
    reuse = await load_shared_arm_reuse(session, trade)
    statuses = await _execute_arms(context, runners, reuse=reuse)
    await apply_tape_pair_assist(session, trade)
    await _persist_statuses(session, work, statuses)
    return EnrichmentAttemptResult(statuses, archive.enrichment_budget_version)


async def _execute_arms(
    context: ArmContext,
    runners: dict[str, ArmRunner],
    *,
    reuse: dict[str, str],
) -> dict[str, str]:
    statuses: dict[str, str] = {}
    for arm in ARM_ORDER:
        statuses[arm] = await _execute_one(arm, context, runners, reuse=reuse)
    return statuses


async def _execute_one(
    arm: str,
    context: ArmContext,
    runners: dict[str, ArmRunner],
    *,
    reuse: dict[str, str],
) -> str:
    if arm in reuse:
        return await _status_from_reuse(arm, context, reuse[arm])
    if arm == "markets":
        return await runners["markets"](context)
    if _budget_blocks(arm, context.ledger):
        return "skipped_budget"
    return await runners[arm](context)


async def _status_from_reuse(arm: str, context: ArmContext, status: str) -> str:
    if arm != "receipt":
        return status
    from polymarket_insider_tracker.ingestor.archive.enrichment_arms import (
        apply_observation_fingerprint,
    )

    context.trade.receipt_status = status
    await apply_observation_fingerprint(context, receipt_status=status)
    return status


async def _persist_statuses(
    session: AsyncSession, work: EnrichmentWorkItemModel, statuses: dict[str, str]
) -> None:
    await FeaturingEnrichmentRepository(session).update_arm_statuses(
        observation_id=work.observation_id,
        trade_ts=work.trade_ts,
        gamma_status=statuses.get("markets"),
        receipt_status=statuses.get("receipt"),
        funding_status=statuses.get("funding"),
        hydrate_status=statuses.get("hydrate"),
    )


def _simulate_arm(
    arm: str,
    *,
    prior: dict[str, str],
    skip: frozenset[str],
    ledger: BudgetLedger,
) -> str:
    if arm in prior:
        return prior[arm]
    if arm == "markets":
        # Snapshot join honesty matches run_markets_arm (not a full Gamma ok).
        return "failed" if arm in skip else "partial"
    return _simulate_degradable(arm, skip=skip, ledger=ledger)


def _simulate_degradable(arm: str, *, skip: frozenset[str], ledger: BudgetLedger) -> str:
    if arm in skip or _budget_blocks(arm, ledger):
        return "skipped_budget"
    _charge_simulated(arm, ledger)
    # Match stub arm honesty (real ok/partial only after producers exist).
    return "pending"


def _budget_blocks(arm: str, ledger: BudgetLedger) -> bool:
    if arm not in DEGRADE_ARMS:
        return False
    if ledger.wall_exhausted():
        return True
    return _resource_blocks(arm, ledger)


def _resource_blocks(arm: str, ledger: BudgetLedger) -> bool:
    if arm in RPC_ARMS:
        return not ledger.can_spend_rpc()
    if arm == "hydrate":
        return not ledger.can_spend_hydrate_page() or ledger.hydrate_time_exhausted()
    return False


def _charge_simulated(arm: str, ledger: BudgetLedger) -> None:
    if arm in RPC_ARMS:
        ledger.spend_rpc(1)
    if arm == "hydrate":
        ledger.hydrate_pages_used += 1


async def _load_trade(
    session: AsyncSession, observation_id: str, trade_ts: datetime
) -> TradeModel | None:
    result = await session.execute(
        select(TradeModel)
        .where(TradeModel.observation_id == observation_id)
        .where(TradeModel.trade_ts == trade_ts)
        .limit(1)
    )
    return result.scalar_one_or_none()
