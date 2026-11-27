"""Tape pair-assist for same-tx counterparties without featuring the other leg."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from polymarket_insider_tracker.ingestor.archive.shared_arms import apply_tape_pair_assist
from polymarket_insider_tracker.storage.models import TradeModel
from tests.ingestor.featured_enrichment_harness import memory_factory, stamp, trade_row


@pytest.mark.asyncio
async def test_unfeatured_opposite_leg_gets_counterparties() -> None:
    engine, factory, _ = await memory_factory()
    ts = stamp()
    async with factory() as session:
        featured = trade_row(observation_id="obs-big", trade_ts=ts, wallet="0xbig", size="20000")
        small = trade_row(
            observation_id="obs-small",
            trade_ts=ts,
            wallet="0xsmall",
            size="10",
            price="0.45",
        )
        session.add_all([featured, small])
        await session.flush()
        wallets = await apply_tape_pair_assist(session, featured)
        assert "0xsmall" in wallets
        assert featured.counterparty_wallets == ["0xsmall"]
        # Small leg never featured: still gets assist if called.
        other = await apply_tape_pair_assist(session, small)
        assert "0xbig" in other
        row = (
            await session.execute(
                select(TradeModel).where(TradeModel.observation_id == "obs-small")
            )
        ).scalar_one()
        assert row.counterparty_wallets == ["0xbig"]
    await engine.dispose()
