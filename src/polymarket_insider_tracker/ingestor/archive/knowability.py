"""Knowability classification lookup (override → series → template → model)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from polymarket_insider_tracker.ingestor.archive.decisions_client import (
    DecisionsClient,
    NullDecisionsClient,
)
from polymarket_insider_tracker.ingestor.archive.knowability_templates import (
    TEMPLATE_ALLOWLIST_VERSION,
    TEMPLATE_MATCHING_ENABLED,
    match_template,
)
from polymarket_insider_tracker.storage.repos import KnowabilityRepository

KNOWABILITY_POLICY_VERSION = "knowability.v1"
VALID_REGIMES = frozenset({"never_early", "always_latent", "windowed", "unknown"})


@dataclass(frozen=True)
class KnowabilityClassification:
    regime: str
    label_source: str
    knowable_from: datetime | None = None
    template_id: str | None = None
    series_slug: str | None = None
    policy_version: str = KNOWABILITY_POLICY_VERSION


class ModelBudget(Protocol):
    def allow(self, day_key: str) -> bool: ...

    def record_success(self) -> None: ...

    def record_error(self) -> None: ...


def onset_for(regime: str, knowable_from: datetime | None) -> datetime | None:
    """Keep onset only for ``windowed`` (null onset = provisional windowed)."""
    if regime != "windowed":
        return None
    return knowable_from


async def _lookup_caches(
    repo: KnowabilityRepository,
    *,
    question: str | None,
    series_slug: str | None,
    category: str | None,
    stamp: datetime,
) -> KnowabilityClassification | None:
    override = await _try_override(
        repo, series_slug=series_slug, question=question, category=category
    )
    if override is not None:
        return override
    series_hit = await _try_series(repo, series_slug)
    if series_hit is not None:
        return series_hit
    if not TEMPLATE_MATCHING_ENABLED:
        return None
    return await _try_template(repo, question=question, category=category, stamp=stamp)


async def classify_market(
    session: AsyncSession,
    *,
    question: str | None,
    series_slug: str | None,
    category: str | None = None,
    market_json: object | None = None,
    decisions: DecisionsClient | None = None,
    model_enabled: bool = False,
    budget: ModelBudget | None = None,
    now: datetime | None = None,
) -> KnowabilityClassification:
    """Lookup order: override → series cache → template → optional Decisions."""
    repo = KnowabilityRepository(session)
    stamp = now if now is not None else datetime.now(UTC)
    cached = await _lookup_caches(
        repo, question=question, series_slug=series_slug, category=category, stamp=stamp
    )
    if cached is not None:
        return cached
    if not model_enabled:
        return KnowabilityClassification(regime="unknown", label_source="unknown")
    return await _try_model(
        repo,
        decisions=decisions or NullDecisionsClient(),
        budget=budget,
        question=question or "",
        series_slug=series_slug,
        market_json=market_json,
        stamp=stamp,
    )


def _override_result(
    *,
    regime: str,
    knowable_from: datetime | None,
    series_slug: str | None = None,
    template_id: str | None = None,
) -> KnowabilityClassification:
    return KnowabilityClassification(
        regime=regime,
        label_source="override",
        knowable_from=onset_for(regime, knowable_from),
        series_slug=series_slug,
        template_id=template_id,
    )


async def _series_override(
    repo: KnowabilityRepository, series_slug: str | None
) -> KnowabilityClassification | None:
    if not series_slug:
        return None
    row = await repo.latest_override(key_type="series", key_id=series_slug)
    if row is None:
        return None
    return _override_result(
        regime=row.regime, knowable_from=row.knowable_from, series_slug=series_slug
    )


async def _template_override(
    repo: KnowabilityRepository,
    *,
    question: str | None,
    category: str | None,
    series_slug: str | None,
) -> KnowabilityClassification | None:
    if not question:
        return None
    match = match_template(question, category=category)
    if match is None:
        return None
    row = await repo.latest_override(key_type="template", key_id=match.template_id)
    if row is None:
        return None
    return _override_result(
        regime=row.regime,
        knowable_from=row.knowable_from,
        series_slug=series_slug,
        template_id=match.template_id,
    )


async def _try_override(
    repo: KnowabilityRepository,
    *,
    series_slug: str | None,
    question: str | None,
    category: str | None,
) -> KnowabilityClassification | None:
    series = await _series_override(repo, series_slug)
    if series is not None:
        return series
    if not TEMPLATE_MATCHING_ENABLED:
        return None
    return await _template_override(
        repo, question=question, category=category, series_slug=series_slug
    )


async def _try_series(
    repo: KnowabilityRepository, series_slug: str | None
) -> KnowabilityClassification | None:
    if not series_slug:
        return None
    row = await repo.latest_series_cache(series_slug, KNOWABILITY_POLICY_VERSION)
    if row is None:
        return None
    return KnowabilityClassification(
        regime=row.regime,
        label_source="series",
        knowable_from=onset_for(row.regime, row.knowable_from),
        series_slug=series_slug,
    )


async def _try_template(
    repo: KnowabilityRepository,
    *,
    question: str | None,
    category: str | None,
    stamp: datetime,
) -> KnowabilityClassification | None:
    if not question:
        return None
    match = match_template(question, category=category)
    if match is None:
        return None
    cached = await repo.latest_template_cache(match.template_id, TEMPLATE_ALLOWLIST_VERSION)
    if cached is None:
        await repo.append_template_cache(
            template_id=match.template_id,
            allowlist_version=TEMPLATE_ALLOWLIST_VERSION,
            regime=match.regime,
            known_at=stamp,
            label_source="template",
        )
        regime = match.regime
    else:
        regime = cached.regime
    return KnowabilityClassification(
        regime=regime,
        label_source="template",
        knowable_from=None,
        template_id=match.template_id,
    )


async def _write_model_series(
    repo: KnowabilityRepository,
    *,
    series_slug: str | None,
    regime: str,
    knowable_from: datetime | None,
    stamp: datetime,
) -> None:
    if not series_slug or regime == "unknown":
        return
    await repo.append_series_cache(
        series_slug=series_slug,
        policy_version=KNOWABILITY_POLICY_VERSION,
        regime=regime,
        known_at=stamp,
        knowable_from=knowable_from,
        label_source="model",
    )


async def _try_model(
    repo: KnowabilityRepository,
    *,
    decisions: DecisionsClient,
    budget: ModelBudget | None,
    question: str,
    series_slug: str | None,
    market_json: object | None,
    stamp: datetime,
) -> KnowabilityClassification:
    if budget is not None and not budget.allow(date_key(stamp)):
        return KnowabilityClassification(regime="unknown", label_source="unknown")
    result = await decisions.classify_regime(
        question=question, series_slug=series_slug, market_json=market_json
    )
    regime = result.regime if result.regime in VALID_REGIMES else "unknown"
    knowable_from = onset_for(regime, _parse_onset(result.knowable_from_iso))
    await _write_model_series(
        repo, series_slug=series_slug, regime=regime, knowable_from=knowable_from, stamp=stamp
    )
    source = "model" if regime != "unknown" else "unknown"
    return KnowabilityClassification(
        regime=regime,
        label_source=source,
        knowable_from=knowable_from,
        series_slug=series_slug,
    )


def date_key(stamp: datetime) -> str:
    return stamp.astimezone(UTC).date().isoformat()


def _parse_onset(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)
