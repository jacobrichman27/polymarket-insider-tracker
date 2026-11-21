"""Edge coverage for TradeArchiveRepository dialect and gap upsert paths."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from polymarket_insider_tracker.storage.models import Base, IngestGapEventModel
from polymarket_insider_tracker.storage.repos import (
    IngestGapEventDTO,
    TradeArchiveRepository,
    TradeTapeDTO,
)

SOURCE = "polymarket:data-api.trades"
OBS = "b" * 64


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        await connection.execute(
            text(
                "CREATE UNIQUE INDEX uq_ingest_gap_ingest_loss_identity "
                "ON ingest_gap_events ("
                "source_id, class, reason, from_time, to_time, detected_at"
                ") WHERE class = 'ingest_loss'"
            )
        )
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with factory() as db:
        yield db
    await engine.dispose()


def _tape() -> TradeTapeDTO:
    now = datetime.now(UTC)
    return TradeTapeDTO(
        trade_ts=now,
        observation_id=OBS,
        observed_at=now,
        archive_start_at=now,
        source_id=SOURCE,
        transaction_hash="0x" + "1" * 64,
        proxy_wallet="0x" + "2" * 40,
        condition_id="0xmarket",
        token_id="token",
        outcome="Yes",
        outcome_index=1,
        side="BUY",
        price=Decimal("0.5"),
        size_shares=Decimal("10"),
        notional_usdc=Decimal("5"),
        source="clob",
        neg_risk=None,
        outcome_repair_status="not_needed",
        outcome_repaired=None,
        outcome_index_repaired=None,
        receipt_status="confirmed",
        info_knowability_regime="unknown",
        knowability_label_source="unknown",
        raw_row_json={"k": "v"},
    )


def _gap(
    *, observation_id: str | None = OBS, reason: str = "archive_insert_failed"
) -> IngestGapEventDTO:
    now = datetime.now(UTC)
    return IngestGapEventDTO(
        source_id=SOURCE,
        class_="write_failure",
        reason=reason,
        from_time=now,
        detected_at=now,
        recorded_at=now,
        status="open",
        observation_id=observation_id,
    )


@pytest.mark.asyncio
async def test_trade_insert_stmt_covers_both_dialects(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = TradeArchiveRepository(session)
    values = repo.trade_values(_tape())
    sqlite_stmt = repo.trade_insert_stmt(values)
    monkeypatch.setattr(repo, "_dialect_name", lambda: "postgresql")
    pg_stmt = repo.trade_insert_stmt(values)
    assert type(sqlite_stmt).__module__.startswith("sqlalchemy")
    assert type(pg_stmt).__module__.startswith("sqlalchemy")
    assert type(sqlite_stmt) is not type(pg_stmt)


@pytest.mark.asyncio
async def test_open_write_failure_updates_existing_and_skips_none_observation(
    session: AsyncSession,
) -> None:
    repo = TradeArchiveRepository(session)
    await repo.open_write_failure(_gap(reason="first"))
    await repo.open_write_failure(_gap(reason="second"))
    await repo.open_write_failure(_gap(observation_id=None, reason="ignored"))
    await session.commit()
    row = (
        await session.execute(
            select(IngestGapEventModel).where(IngestGapEventModel.observation_id == OBS)
        )
    ).scalar_one()
    assert row.reason == "second"
    assert len((await session.execute(select(IngestGapEventModel))).scalars().all()) == 1


@pytest.mark.asyncio
async def test_mirror_ingest_loss_ignores_duplicate_identity(session: AsyncSession) -> None:
    repo = TradeArchiveRepository(session)
    now = datetime.now(UTC)
    dto = IngestGapEventDTO(
        source_id=SOURCE,
        class_="ingest_loss",
        reason="horizon-expired",
        from_time=now,
        to_time=now,
        detected_at=now,
        recorded_at=now,
        status="open",
        pages_examined=1,
    )
    await repo.mirror_ingest_loss(dto)
    await repo.mirror_ingest_loss(dto)
    await session.commit()
    rows = (await session.execute(select(IngestGapEventModel))).scalars().all()
    assert len(rows) == 1
