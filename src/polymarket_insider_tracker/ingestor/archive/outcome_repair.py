"""Forward-only async outcome repair."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

from polymarket_insider_tracker.ingestor.archive.markets import snapshot_at
from polymarket_insider_tracker.storage.repos import TradeArchiveRepository

THIN_OUTCOME_INDEX = 999
STATUS_NOT_NEEDED = "not_needed"
STATUS_OK = "ok"
STATUS_UNREPAIRED = "unrepaired"


@dataclass(frozen=True)
class RepairDecision:
    status: str
    outcome_repaired: str | None = None
    outcome_index_repaired: int | None = None


def api_outcome_usable(outcome: str | None, outcome_index: int | None) -> bool:
    if outcome_index == THIN_OUTCOME_INDEX:
        return False
    return outcome is not None and bool(str(outcome).strip())


def _map_token(token_id: str, token_outcomes: dict[str, Any]) -> RepairDecision:
    mapped_obj = token_outcomes.get(token_id)
    if not isinstance(mapped_obj, dict):
        return RepairDecision(status=STATUS_UNREPAIRED)
    mapped = cast(dict[str, Any], mapped_obj)
    label_obj: object | None = mapped.get("outcome")
    index_int = _as_int(mapped.get("outcome_index"))
    if label_obj is None or str(label_obj).strip() == "" or index_int is None:
        return RepairDecision(status=STATUS_UNREPAIRED)
    return RepairDecision(
        status=STATUS_OK,
        outcome_repaired=str(label_obj),
        outcome_index_repaired=index_int,
    )


def decide_repair(
    *,
    outcome: str | None,
    outcome_index: int | None,
    token_id: str,
    token_outcomes: dict[str, Any] | None,
) -> RepairDecision:
    """Never invent. Usable API → not_needed; thin → map or unrepaired."""
    if api_outcome_usable(outcome, outcome_index):
        return RepairDecision(status=STATUS_NOT_NEEDED)
    if not token_outcomes:
        return RepairDecision(status=STATUS_UNREPAIRED)
    return _map_token(token_id, token_outcomes)


def _as_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def is_post_cutover(observed_at: datetime, repair_enabled_at: datetime | None) -> bool:
    if repair_enabled_at is None:
        return False
    return observed_at >= repair_enabled_at


async def repair_trade_row(
    session: AsyncSession,
    *,
    trade_ts: datetime,
    observation_id: str,
    observed_at: datetime,
    condition_id: str,
    token_id: str,
    outcome: str | None,
    outcome_index: int | None,
    repair_enabled_at: datetime | None,
) -> RepairDecision | None:
    """Apply forward-only repair for one post-cutover row. Pre-cutover → None."""
    if not is_post_cutover(observed_at, repair_enabled_at):
        return None
    if api_outcome_usable(outcome, outcome_index):
        decision = RepairDecision(status=STATUS_NOT_NEEDED)
        await _persist(session, trade_ts, observation_id, decision)
        return decision
    snap = await snapshot_at(session, condition_id=condition_id, at=trade_ts)
    outcomes = snap.token_outcomes if snap is not None else None
    decision = decide_repair(
        outcome=outcome,
        outcome_index=outcome_index,
        token_id=token_id,
        token_outcomes=outcomes,
    )
    await _persist(session, trade_ts, observation_id, decision)
    return decision


async def _persist(
    session: AsyncSession,
    trade_ts: datetime,
    observation_id: str,
    decision: RepairDecision,
) -> None:
    repo = TradeArchiveRepository(session)
    await repo.update_outcome_repair(
        trade_ts=trade_ts,
        observation_id=observation_id,
        status=decision.status,
        outcome_repaired=decision.outcome_repaired,
        outcome_index_repaired=decision.outcome_index_repaired,
    )
