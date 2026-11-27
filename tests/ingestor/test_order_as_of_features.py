"""live_as_of immutability / fully_enriched rematerialize."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from polymarket_insider_tracker.ingestor.archive.trade_features import (
    materialize_fully_enriched,
    materialize_live_as_of,
)
from polymarket_insider_tracker.storage.models import Base


@pytest.mark.asyncio
async def test_live_as_of_not_overwritten_in_place() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    trade_ts = datetime(2026, 11, 25, tzinfo=UTC)
    async with factory() as session:
        first = await materialize_live_as_of(
            session,
            observation_id="obs",
            trade_ts=trade_ts,
            feature_version="b.v1",
            enrichment_budget_version="b.v1",
            fingerprint_version="b.v1",
            payload={"rank": 1},
        )
        second = await materialize_live_as_of(
            session,
            observation_id="obs",
            trade_ts=trade_ts,
            feature_version="b.v1",
            enrichment_budget_version="b.v1",
            fingerprint_version="b.v1",
            payload={"rank": 99},
        )
        enriched = await materialize_fully_enriched(
            session,
            observation_id="obs",
            trade_ts=trade_ts,
            feature_version="b.v1",
            enrichment_budget_version="b.v1",
            fingerprint_version="b.v1",
            payload={"rank": 2},
        )
        await session.commit()
        assert first is not None
        assert second is None
        assert enriched.order_as_of_contract == "fully_enriched"
        assert first.payload == {"rank": 1}
    await engine.dispose()
