"""Proxy funding arm: Transfer-log stub until a real lookup exists."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from polymarket_insider_tracker.ingestor.archive.enrichment import ArmContext
from polymarket_insider_tracker.storage.models import ProxyFundingModel

__all__ = ["run_funding_arm", "append_proxy_funding"]

_STUB_WRITER = "transfer_logs_stub"


async def run_funding_arm(context: ArmContext) -> str:
    """Stub funding status only — no RPC burn and no Dune call."""
    existing = await _latest_funding(context)
    if existing is not None and existing.funding_lookup_status == "ok":
        return "ok"
    if existing is not None and _is_stub_funding(existing):
        return existing.funding_lookup_status
    await append_proxy_funding(
        context,
        status="pending",
        funding_source=None,
        first_funding_exact=None,
    )
    return "pending"


async def append_proxy_funding(
    context: ArmContext,
    *,
    status: str,
    funding_source: str | None,
    first_funding_exact: bool | None,
) -> ProxyFundingModel:
    model = ProxyFundingModel(
        proxy_wallet=context.trade.proxy_wallet,
        known_at=datetime.now(UTC),
        funding_lookup_status=status,
        funding_source=funding_source,
        owner_address=None,
        wallet_type=None,
        wallet_created_at=None,
        first_funding_exact=first_funding_exact,
        payload={"writer": _STUB_WRITER},
    )
    context.session.add(model)
    await context.session.flush()
    return model


def _is_stub_funding(row: ProxyFundingModel) -> bool:
    if not isinstance(row.payload, dict):
        return False
    return row.payload.get("writer") == _STUB_WRITER


async def _latest_funding(context: ArmContext) -> ProxyFundingModel | None:
    result = await context.session.execute(
        select(ProxyFundingModel)
        .where(ProxyFundingModel.proxy_wallet == context.trade.proxy_wallet)
        .order_by(ProxyFundingModel.known_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()
