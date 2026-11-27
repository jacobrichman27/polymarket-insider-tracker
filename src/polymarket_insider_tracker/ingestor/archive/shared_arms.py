"""Shared enrichment-arm reuse by grain + tape pair-assist for counterparties."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from polymarket_insider_tracker.storage.models import TradeModel

__all__ = ["apply_tape_pair_assist", "load_shared_arm_reuse"]

_RECEIPT_REUSE = frozenset({"ok", "partial", "pending", "failed", "skipped_budget"})
_FUNDING_REUSE = frozenset({"ok", "partial", "pending", "miss", "hit", "failed", "skipped_budget"})
_HYDRATE_REUSE = frozenset({"ok", "partial", "pending", "miss", "failed", "skipped_budget"})


async def load_shared_arm_reuse(session: AsyncSession, trade: TradeModel) -> dict[str, str]:
    """Reuse receipt by tx; funding/hydrate by proxy (not this observation)."""
    reuse: dict[str, str] = {}
    receipt = await _sibling_receipt_status(session, trade)
    if receipt is not None:
        reuse["receipt"] = receipt
    funding = await _sibling_status(
        session, trade, column="funding_lookup_status", allowed=_FUNDING_REUSE
    )
    if funding is not None:
        reuse["funding"] = funding
    hydrate = await _sibling_status(
        session, trade, column="wallet_hydrate_status", allowed=_HYDRATE_REUSE
    )
    if hydrate is not None:
        reuse["hydrate"] = hydrate
    return reuse


async def apply_tape_pair_assist(session: AsyncSession, trade: TradeModel) -> list[str]:
    """Set counterparty_wallets from same-tx tape legs (featured or not)."""
    result = await session.execute(
        select(TradeModel.proxy_wallet)
        .where(TradeModel.transaction_hash == trade.transaction_hash)
        .where(TradeModel.observation_id != trade.observation_id)
    )
    wallets = [row[0] for row in result.all() if row[0] and row[0] != trade.proxy_wallet]
    unique = sorted(set(wallets))
    if unique:
        trade.counterparty_wallets = unique
        await session.flush()
    return unique


async def _sibling_receipt_status(session: AsyncSession, trade: TradeModel) -> str | None:
    result = await session.execute(
        select(TradeModel.receipt_status)
        .where(TradeModel.transaction_hash == trade.transaction_hash)
        .where(TradeModel.observation_id != trade.observation_id)
        .where(TradeModel.receipt_status.in_(_RECEIPT_REUSE))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _sibling_status(
    session: AsyncSession,
    trade: TradeModel,
    *,
    column: str,
    allowed: frozenset[str],
) -> str | None:
    col = getattr(TradeModel, column)
    result = await session.execute(
        select(col)
        .where(TradeModel.proxy_wallet == trade.proxy_wallet)
        .where(TradeModel.observation_id != trade.observation_id)
        .where(col.in_(allowed))
        .limit(1)
    )
    return result.scalar_one_or_none()
