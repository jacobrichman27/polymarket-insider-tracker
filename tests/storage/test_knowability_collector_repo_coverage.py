"""Direct coverage for collector cutover and template-cache repository helpers."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from polymarket_insider_tracker.storage.models import Base
from polymarket_insider_tracker.storage.repos import KnowabilityRepository, TradeArchiveRepository


@pytest.mark.asyncio
async def test_repair_cutover_once_semantics() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    async with factory() as session:
        repo = TradeArchiveRepository(session)
        with pytest.raises(ValueError, match="no collector state"):
            await repo.set_repair_enabled_at_once(source_id="src", repair_enabled_at=now)
        await repo.insert_collector_state(source_id="src", archive_start_at=now, raw_retention=True)
        first = await repo.set_repair_enabled_at_once(source_id="src", repair_enabled_at=now)
        assert first.repair_enabled_at == now
        second = await repo.set_repair_enabled_at_once(
            source_id="src", repair_enabled_at=datetime(2099, 1, 1, tzinfo=UTC)
        )
        assert second.repair_enabled_at == now
    await engine.dispose()


@pytest.mark.asyncio
async def test_template_cache_append_and_latest() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    now = datetime.now(UTC)
    async with factory() as session:
        repo = KnowabilityRepository(session)
        assert await repo.latest_template_cache("tpl", "allow.v1") is None
        await repo.append_template_cache(
            template_id="tpl",
            allowlist_version="allow.v1",
            regime="private_edge_possible",
            known_at=now,
            label_source="template",
        )
        await session.commit()
        hit = await repo.latest_template_cache("tpl", "allow.v1")
        assert hit is not None
        assert hit.regime == "private_edge_possible"
    await engine.dispose()
