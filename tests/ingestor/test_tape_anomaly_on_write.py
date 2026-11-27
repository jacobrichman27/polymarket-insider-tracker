"""ArchiveWriter.write records tape anomaly kinds."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from polymarket_insider_tracker.ingestor.archive.tape_anomaly import (
    anomaly_counts,
    clear_anomaly_counts,
)
from polymarket_insider_tracker.ingestor.archive.writer import ArchiveWriter
from polymarket_insider_tracker.ingestor.trade_rows import TradeObservation, parse_trade_row
from tests.fakes.trades import trade_row
from tests.ingestor.featured_enrichment_harness import memory_factory

NOW = 1_788_983_720
SOURCE = "polymarket:data-api.trades"


def _obs() -> TradeObservation:
    parsed = parse_trade_row(
        trade_row(timestamp=NOW - 5, transaction=42, wallet=7, price="0.55", size="100"),
        now=NOW,
    )
    assert isinstance(parsed, TradeObservation)
    return parsed


@pytest.mark.asyncio
async def test_writer_increments_thin_and_price_anomalies() -> None:
    clear_anomaly_counts()
    engine, factory, _ = await memory_factory()
    obs = _obs()
    weird = replace(
        obs,
        event=replace(
            obs.event,
            outcome="",
            outcome_index=999,
            price=Decimal("1.25"),
        ),
        raw_row=None,
    )
    async with factory() as session:
        writer = ArchiveWriter(session, source_id=SOURCE, raw_retention=True)
        await writer.write(weird)
        await session.commit()
    counts = anomaly_counts()
    assert counts.get("thin_outcome", 0) >= 1
    assert counts.get("price_out_of_range", 0) >= 1
    assert counts.get("missing_raw_row", 0) >= 1
    await engine.dispose()
