"""Exact question-text cache: write-through on model hit; reuse across condition ids."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from polymarket_insider_tracker.ingestor.archive.decisions_client import DecisionsRegimeResult
from polymarket_insider_tracker.ingestor.archive.knowability import (
    KNOWABILITY_POLICY_VERSION,
    classify_market,
    normalize_question_text,
)
from polymarket_insider_tracker.storage.models import Base
from polymarket_insider_tracker.storage.repos import KnowabilityRepository

SessionFactory = async_sessionmaker[AsyncSession]


class _CountingDecisions:
    def __init__(self, regime: str = "no_private_edge") -> None:
        self.calls = 0
        self._regime = regime

    async def classify_regime(
        self,
        *,
        question: str,
        series_slug: str | None,
        market_json: object | None,
    ) -> DecisionsRegimeResult:
        del question, series_slug, market_json
        self.calls += 1
        return DecisionsRegimeResult(regime=self._regime)


@pytest.fixture
async def session_factory() -> AsyncGenerator[SessionFactory, None]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory: SessionFactory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory
    await engine.dispose()


def test_normalize_question_collapses_case_and_whitespace() -> None:
    left = normalize_question_text("  Will ETH Dip To $1,200?  ")
    right = normalize_question_text("will eth dip to $1,200?")
    assert left is not None and right is not None
    assert left.key == right.key
    assert left.text == "will eth dip to $1,200?"


def test_normalize_rejects_blank() -> None:
    assert normalize_question_text(None) is None
    assert normalize_question_text("   ") is None


@pytest.mark.asyncio
async def test_model_write_through_serves_second_market(
    session_factory: SessionFactory,
) -> None:
    decisions = _CountingDecisions("no_private_edge")
    question = "Will Ethereum dip to $1,200 November 23-29?"
    stamp = datetime(2026, 11, 25, 22, 0, tzinfo=UTC)
    async with session_factory() as session:
        first = await classify_market(
            session,
            question=question,
            series_slug=None,
            decisions=decisions,
            model_enabled=True,
            now=stamp,
        )
        await session.commit()
    assert first.label_source == "model"
    assert first.regime == "no_private_edge"
    assert decisions.calls == 1

    async with session_factory() as session:
        second = await classify_market(
            session,
            question=f"  {question.upper()} ",
            series_slug=None,
            decisions=decisions,
            model_enabled=True,
            now=stamp,
        )
    assert second.regime == "no_private_edge"
    assert second.label_source == "question"
    assert decisions.calls == 1


@pytest.mark.asyncio
async def test_series_beats_question_cache(session_factory: SessionFactory) -> None:
    stamp = datetime(2026, 11, 25, tzinfo=UTC)
    question = "Same title different sources"
    normalized = normalize_question_text(question)
    assert normalized is not None
    async with session_factory() as session:
        repo = KnowabilityRepository(session)
        await repo.append_question_cache(
            question_key=normalized.key,
            question_text=normalized.text,
            policy_version=KNOWABILITY_POLICY_VERSION,
            regime="no_private_edge",
            known_at=stamp,
            label_source="model",
        )
        await repo.append_series_cache(
            series_slug="series-q",
            policy_version=KNOWABILITY_POLICY_VERSION,
            regime="private_edge_possible",
            known_at=stamp,
            label_source="series",
        )
        await session.commit()
        result = await classify_market(
            session,
            question=question,
            series_slug="series-q",
            model_enabled=False,
        )
    assert result.regime == "private_edge_possible"
    assert result.label_source == "series"


@pytest.mark.asyncio
async def test_unknown_model_result_does_not_seed_question_cache(
    session_factory: SessionFactory,
) -> None:
    decisions = _CountingDecisions("unknown")
    async with session_factory() as session:
        result = await classify_market(
            session,
            question="Ambiguous listing?",
            series_slug=None,
            decisions=decisions,
            model_enabled=True,
        )
        await session.commit()
        assert result.label_source == "unknown"
        normalized = normalize_question_text("Ambiguous listing?")
        assert normalized is not None
        cached = await KnowabilityRepository(session).latest_question_cache(
            normalized.key, KNOWABILITY_POLICY_VERSION
        )
        assert cached is None
