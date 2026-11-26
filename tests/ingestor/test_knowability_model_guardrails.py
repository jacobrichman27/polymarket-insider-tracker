"""Model budget / circuit / credentials-absent guardrails (US4)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from polymarket_insider_tracker.ingestor.archive.decisions_client import (
    BudgetGate,
    DecisionsRegimeResult,
)
from polymarket_insider_tracker.ingestor.archive.knowability import classify_market
from polymarket_insider_tracker.storage.models import Base


class _CountingDecisions:
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


@pytest.mark.asyncio
async def test_over_budget_returns_unknown_without_call() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    decisions = _CountingDecisions()
    budget = BudgetGate(max_calls_per_day=0)
    async with factory() as session:
        result = await classify_market(
            session,
            question="Obscure market with no template cues",
            series_slug=None,
            decisions=decisions,
            model_enabled=True,
            budget=budget,
            now=datetime(2026, 11, 24, tzinfo=UTC),
        )
    assert result.regime == "unknown"
    assert decisions.calls == 0
    await engine.dispose()


@pytest.mark.asyncio
async def test_model_disabled_leaves_unknown() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    decisions = _CountingDecisions()
    async with factory() as session:
        result = await classify_market(
            session,
            question="Obscure market with no template cues",
            series_slug=None,
            decisions=decisions,
            model_enabled=False,
        )
    assert result.regime == "unknown"
    assert decisions.calls == 0
    await engine.dispose()


def test_circuit_opens_after_errors() -> None:
    gate = BudgetGate(max_calls_per_day=100, error_threshold=2)
    assert gate.allow("2026-11-24") is True
    gate.record_error()
    gate.record_error()
    assert gate.circuit_open is True
    assert gate.allow("2026-11-24") is False
