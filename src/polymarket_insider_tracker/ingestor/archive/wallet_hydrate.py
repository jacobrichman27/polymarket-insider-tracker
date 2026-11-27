"""Lifetime hydrate arm and versioned wallets writes."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from polymarket_insider_tracker.ingestor.archive.enrichment import ArmContext
from polymarket_insider_tracker.storage.models import ArchiveWalletModel

__all__ = [
    "is_stub_hydrate_payload",
    "lifetime_is_first_trade_value",
    "require_hydrate_status",
    "run_hydrate_arm",
]

_STUB_SOURCE = "data_api_stub"


def lifetime_is_first_trade_value(*, complete: bool, empty_walk: bool) -> bool | None:
    """True only on a complete empty hydrate walk; else null."""
    if complete and empty_walk:
        return True
    return None


def require_hydrate_status(status: str | None) -> str:
    """Analysis must stratify by wallet_hydrate_status; reject silent hybrids."""
    if status is None or status == "":
        raise ValueError("wallet_hydrate_status required for hydrate/archive hybrid analysis")
    return status


def is_stub_hydrate_payload(payload: object | None) -> bool:
    if not isinstance(payload, dict):
        return False
    return payload.get("source") == _STUB_SOURCE


async def run_hydrate_arm(context: ArmContext) -> str:
    if not context.ledger.can_spend_hydrate_page():
        return "skipped_budget"
    existing = await _latest_wallet(context)
    if existing is not None and _reusable_hydrate_status(existing):
        return existing.wallet_hydrate_status
    context.ledger.hydrate_pages_used += 1
    # No Data-API walk yet: never claim ok.
    status = "pending"
    model = ArchiveWalletModel(
        proxy_wallet=context.trade.proxy_wallet,
        known_at=datetime.now(UTC),
        wallet_hydrate_status=status,
        lifetime_is_first_trade=None,
        payload={"source": _STUB_SOURCE},
        event_horizon_at=None,
    )
    context.session.add(model)
    await context.session.flush()
    return status


def _reusable_hydrate_status(existing: ArchiveWalletModel) -> bool:
    if existing.wallet_hydrate_status == "ok" and not is_stub_hydrate_payload(existing.payload):
        return True
    return existing.wallet_hydrate_status == "pending" and is_stub_hydrate_payload(existing.payload)


async def _latest_wallet(context: ArmContext) -> ArchiveWalletModel | None:
    result = await context.session.execute(
        select(ArchiveWalletModel)
        .where(ArchiveWalletModel.proxy_wallet == context.trade.proxy_wallet)
        .order_by(ArchiveWalletModel.known_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()
