"""Knowability lookup order: override → series → question → template → model."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from polymarket_insider_tracker.ingestor.archive.decisions_client import DecisionsRegimeResult
from polymarket_insider_tracker.ingestor.archive.knowability import (
    KNOWABILITY_POLICY_VERSION,
    classify_market,
)
from polymarket_insider_tracker.storage.models import Base
from polymarket_insider_tracker.storage.repos import KnowabilityRepository

SessionFactory = async_sessionmaker[AsyncSession]


class _FakeDecisions:
    def __init__(self) -> None:
        self.calls = 0

    async def classify_regime(
        self,
        *,
        question: str,
        series_slug: str | None,
        market_json: object | None,
    ) -> DecisionsRegimeResult:
        del question, series_slug, market_json
        self.calls += 1
        return DecisionsRegimeResult(regime="private_edge_possible")


@pytest.fixture
async def session_factory() -> AsyncGenerator[SessionFactory, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory: SessionFactory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_override_beats_series_and_model(session_factory: SessionFactory) -> None:
    stamp = datetime(2026, 11, 24, tzinfo=UTC)
    decisions = _FakeDecisions()
    async with session_factory() as session:
        repo = KnowabilityRepository(session)
        await repo.append_override(
            key_type="series",
            key_id="series-a",
            known_at=stamp,
            regime="no_private_edge",
            policy_version=KNOWABILITY_POLICY_VERSION,
        )
        await repo.append_series_cache(
            series_slug="series-a",
            policy_version=KNOWABILITY_POLICY_VERSION,
            regime="private_edge_possible",
            known_at=stamp,
            label_source="series",
        )
        await session.commit()
        result = await classify_market(
            session,
            question="Will BTC be up or down on 2026-11-24?",
            series_slug="series-a",
            decisions=decisions,
            model_enabled=True,
        )
    assert result.regime == "no_private_edge"
    assert result.label_source == "override"
    assert decisions.calls == 0


@pytest.mark.asyncio
async def test_legacy_policy_override_is_ignored(session_factory: SessionFactory) -> None:
    stamp = datetime(2026, 11, 24, tzinfo=UTC)
    async with session_factory() as session:
        repo = KnowabilityRepository(session)
        await repo.append_override(
            key_type="series",
            key_id="series-legacy",
            known_at=stamp,
            regime="always_latent",
            policy_version="knowability.v1",
        )
        await session.commit()
        result = await classify_market(
            session,
            question="Will the committee approve the nominee?",
            series_slug="series-legacy",
            model_enabled=False,
        )
    assert result.regime == "unknown"
    assert result.label_source == "unknown"


@pytest.mark.asyncio
async def test_title_rule_skips_model_for_temperature(
    session_factory: SessionFactory,
) -> None:
    decisions = _FakeDecisions()
    async with session_factory() as session:
        result = await classify_market(
            session,
            question="Will the highest temperature in Paris be -2°C on November 28?",
            series_slug="weather-paris",
            decisions=decisions,
            model_enabled=True,
        )
    assert result.regime == "no_private_edge"
    assert result.label_source == "title_rule"
    assert decisions.calls == 0


@pytest.mark.asyncio
async def test_series_beats_template(session_factory: SessionFactory) -> None:
    stamp = datetime(2026, 11, 24, tzinfo=UTC)
    async with session_factory() as session:
        repo = KnowabilityRepository(session)
        await repo.append_series_cache(
            series_slug="series-b",
            policy_version=KNOWABILITY_POLICY_VERSION,
            regime="private_edge_possible",
            known_at=stamp,
            label_source="series",
        )
        await session.commit()
        result = await classify_market(
            session,
            question="Will BTC be up or down on 2026-11-24?",
            series_slug="series-b",
            model_enabled=False,
        )
    assert result.regime == "private_edge_possible"
    assert result.label_source == "series"
