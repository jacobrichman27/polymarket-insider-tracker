"""Optional featured trade_features snapshots with order-as-of contracts."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from polymarket_insider_tracker.storage.models import TradeFeaturesModel
from polymarket_insider_tracker.storage.repos import FeaturingEnrichmentRepository

__all__ = ["materialize_live_as_of", "materialize_fully_enriched"]


async def materialize_live_as_of(
    session: AsyncSession,
    *,
    observation_id: str,
    trade_ts: datetime,
    feature_version: str,
    enrichment_budget_version: str,
    fingerprint_version: str,
    payload: object,
) -> TradeFeaturesModel | None:
    """Insert live_as_of row; refuse in-place overwrite if one already exists."""
    return await FeaturingEnrichmentRepository(session).insert_live_as_of_features(
        observation_id=observation_id,
        trade_ts=trade_ts,
        feature_version=feature_version,
        enrichment_budget_version=enrichment_budget_version,
        fingerprint_version=fingerprint_version,
        payload=payload,
        materialized_at=datetime.now(UTC),
    )


async def materialize_fully_enriched(
    session: AsyncSession,
    *,
    observation_id: str,
    trade_ts: datetime,
    feature_version: str,
    enrichment_budget_version: str,
    fingerprint_version: str,
    payload: object,
) -> TradeFeaturesModel:
    """Always write a new fully_enriched row (never mutates live_as_of)."""
    model = TradeFeaturesModel(
        observation_id=observation_id,
        trade_ts=trade_ts,
        feature_version=feature_version,
        order_as_of_contract="fully_enriched",
        enrichment_budget_version=enrichment_budget_version,
        fingerprint_version=fingerprint_version,
        payload=payload,
        materialized_at=datetime.now(UTC),
    )
    session.add(model)
    await session.flush()
    return model
