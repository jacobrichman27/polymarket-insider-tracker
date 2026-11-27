"""Default enrichment arm runners (markets / receipt / funding / hydrate)."""

from __future__ import annotations

from polymarket_insider_tracker.ingestor.archive.enrichment import ArmContext, ArmRunner
from polymarket_insider_tracker.ingestor.archive.fingerprint import compute_fill_fingerprint
from polymarket_insider_tracker.ingestor.archive.funding_sync import run_funding_arm
from polymarket_insider_tracker.ingestor.archive.trade_features import materialize_live_as_of
from polymarket_insider_tracker.ingestor.archive.wallet_hydrate import run_hydrate_arm
from polymarket_insider_tracker.storage.repos import MarketsRepository

__all__ = [
    "apply_observation_fingerprint",
    "default_arm_runners",
    "run_markets_arm",
    "run_receipt_arm",
]

_LIVE_AS_OF_RECEIPT = frozenset({"ok", "partial"})


async def run_markets_arm(context: ArmContext) -> str:
    """Markets/Gamma arm: A1 snapshot join → ``partial``; miss → ``failed``.

    Status is stored on ``trades.gamma_enrichment_status`` (arm key remains
    ``markets`` in orchestration). Never claim ``ok`` without a live Gamma refresh.
    """
    row = await MarketsRepository(context.session).latest_at_or_before(
        context.trade.condition_id, context.trade.trade_ts
    )
    if row is None:
        return "failed"
    return "partial"


async def run_receipt_arm(context: ArmContext) -> str:
    """Receipt decode arm; charges one RPC when attempting."""
    if not context.ledger.can_spend_rpc():
        return "skipped_budget"
    context.ledger.spend_rpc(1)
    if context.trade.transaction_hash:
        context.trade.receipt_status = "pending"
        return "pending"
    return "failed"


async def apply_observation_fingerprint(context: ArmContext, *, receipt_status: str) -> None:
    """Per-observation fingerprint; live_as_of only after receipt ok/partial."""
    result = compute_fill_fingerprint(
        transaction_hash=context.trade.transaction_hash,
        token_id=context.trade.token_id,
        fingerprint_version=context.archive.fingerprint_version,
        log_index=context.trade.log_index,
        price=context.trade.price,
        size_shares=context.trade.size_shares,
    )
    context.trade.fill_fingerprint = result.fill_fingerprint
    context.trade.fingerprint_version = result.fingerprint_version
    if receipt_status not in _LIVE_AS_OF_RECEIPT:
        return
    await materialize_live_as_of(
        context.session,
        observation_id=context.trade.observation_id,
        trade_ts=context.trade.trade_ts,
        feature_version=context.archive.feature_version,
        enrichment_budget_version=context.archive.enrichment_budget_version,
        fingerprint_version=result.fingerprint_version,
        payload={"strength": result.strength},
    )


async def _run_receipt_and_fingerprint(context: ArmContext) -> str:
    status = await run_receipt_arm(context)
    await apply_observation_fingerprint(context, receipt_status=status)
    return status


def default_arm_runners() -> dict[str, ArmRunner]:
    return {
        "markets": run_markets_arm,
        "receipt": _run_receipt_and_fingerprint,
        "funding": run_funding_arm,
        "hydrate": run_hydrate_arm,
    }
