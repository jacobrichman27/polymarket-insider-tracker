"""Coverage for production archive bind helpers on PipelineComponents."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import cast

import pytest
from fakeredis import FakeAsyncRedis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from polymarket_insider_tracker.ingestor.archive import gap_ledger
from polymarket_insider_tracker.ingestor.archive.health import ArchiveHealthSignals
from polymarket_insider_tracker.ingestor.archive.metrics import PrometheusArchiveMetrics
from polymarket_insider_tracker.ingestor.archive.writer import (
    ArchiveWriter,
    ArchiveWriteResult,
    ArchiveWriteStatus,
    NullArchiveMetrics,
)
from polymarket_insider_tracker.ingestor.models import TradeEvent
from polymarket_insider_tracker.ingestor.observation_boundary import LossEvent, LossReason
from polymarket_insider_tracker.ingestor.trade_poller import IngestionState
from polymarket_insider_tracker.ingestor.trade_rows import TradeObservation, parse_trade_row
from polymarket_insider_tracker.pipeline_components import (
    bind_abandon_write,
    bind_archive_write,
    bind_loss_mirror,
    build_components,
    persist_archive_observation,
    publish_owed_metrics,
)
from polymarket_insider_tracker.storage.database import DatabaseManager
from polymarket_insider_tracker.storage.models import Base, IngestGapEventModel, TradeModel
from tests.fakes import make_test_settings, trade_row

NOW = 1_788_983_720
SOURCE = "polymarket:data-api.trades"


class SessionDatabase:
    """Duck-typed session factory matching ``DatabaseManager.get_async_session``."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @asynccontextmanager
    async def get_async_session(self) -> AsyncGenerator[AsyncSession, None]:
        yield self._session

    async def dispose_async(self) -> None:
        return None


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with factory() as db:
        yield db
    await engine.dispose()


def _observation() -> TradeObservation:
    parsed = parse_trade_row(trade_row(timestamp=NOW - 3, transaction=9, wallet=3), now=NOW)
    assert isinstance(parsed, TradeObservation)
    return parsed


def _db(session: AsyncSession) -> DatabaseManager:
    return cast(DatabaseManager, SessionDatabase(session))


@pytest.mark.asyncio
async def test_bind_archive_write_persists_and_clears_owed(session: AsyncSession) -> None:
    settings = make_test_settings(archive_enabled=True)
    health = ArchiveHealthSignals()
    write = bind_archive_write(settings, _db(session), SOURCE, health)
    observation = _observation()
    assert await write(observation) is True
    assert health.owed_count() == 0
    assert (await session.execute(select(TradeModel))).scalar_one() is not None


@pytest.mark.asyncio
async def test_bind_archive_write_failure_marks_metrics(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _fail(_self: ArchiveWriter, observation: TradeObservation) -> ArchiveWriteResult:
        return ArchiveWriteResult(
            status=ArchiveWriteStatus.FAILED,
            observation_id=observation.identity,
            detail="boom",
        )

    monkeypatch.setattr(ArchiveWriter, "write", _fail)
    settings = make_test_settings(archive_enabled=True)
    health = ArchiveHealthSignals()
    write = bind_archive_write(settings, _db(session), SOURCE, health)
    assert await write(_observation()) is False
    assert health.owed_count() == 1


@pytest.mark.asyncio
async def test_persist_and_publish_helpers(session: AsyncSession) -> None:
    observation = _observation()
    health = ArchiveHealthSignals()
    health.mark_owed(observation.identity, float(NOW))
    ok = await persist_archive_observation(
        _db(session), SOURCE, True, NullArchiveMetrics(), observation
    )
    assert ok is True
    publish_owed_metrics(health, PrometheusArchiveMetrics(), float(NOW))


@pytest.mark.asyncio
async def test_build_components_wires_archive_when_enabled(
    session: AsyncSession,
    fake_redis: FakeAsyncRedis,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Factory:
        @classmethod
        def from_url(cls, url: str) -> FakeAsyncRedis:
            del url
            return fake_redis

    def _redis_factory() -> type[_Factory]:
        return _Factory

    def _database_manager(url: str, async_mode: bool = True) -> SessionDatabase:
        del url, async_mode
        return SessionDatabase(session)

    monkeypatch.setattr(
        "polymarket_insider_tracker.pipeline_components._redis_factory",
        _redis_factory,
    )
    monkeypatch.setattr(
        "polymarket_insider_tracker.pipeline_components.DatabaseManager",
        _database_manager,
    )

    async def on_trade(trade: TradeEvent) -> None:
        del trade

    def on_state(state: IngestionState) -> None:
        del state

    settings = make_test_settings(archive_enabled=True)
    components = await build_components(
        settings,
        dry_run=True,
        on_trade=on_trade,
        on_ingestion_state=on_state,
        archive_health=ArchiveHealthSignals(),
    )
    again = await build_components(
        settings, dry_run=True, on_trade=on_trade, on_ingestion_state=on_state
    )
    assert components.trade_poller is not None
    assert again.trade_poller is not None
    if components.db_manager is not None:
        await components.db_manager.dispose_async()
    if again.db_manager is not None:
        await again.db_manager.dispose_async()
    await components.redis.aclose()
    await again.redis.aclose()


@pytest.mark.asyncio
async def test_loss_mirror_and_abandon_bindings(session: AsyncSession) -> None:
    health = ArchiveHealthSignals()
    observation = _observation()
    health.mark_owed(observation.identity, float(NOW))
    mirror = bind_loss_mirror(_db(session), SOURCE)
    abandon = bind_abandon_write(_db(session), SOURCE, health)
    await mirror(
        LossEvent(
            from_time=100,
            to_time=200,
            reason=LossReason.HORIZON_EXPIRED,
            detected_at=210,
            recorded_at=211,
            pages_examined=2,
        )
    )
    await gap_ledger.record_write_failure(
        session, source_id=SOURCE, observation_id=observation.identity
    )
    await abandon(observation)
    assert health.owed_count() == 0
    classes = {row.class_ for row in (await session.execute(select(IngestGapEventModel))).scalars()}
    assert "ingest_loss" in classes
