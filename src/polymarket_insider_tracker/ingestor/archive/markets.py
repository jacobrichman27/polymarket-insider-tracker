"""Append-on-change versioned markets writer and snapshot join."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy.ext.asyncio import AsyncSession

from polymarket_insider_tracker.storage.repos import MarketsRepository


@dataclass(frozen=True)
class MarketSnapshot:
    condition_id: str
    known_at: datetime
    token_outcomes: dict[str, Any]
    question: str | None = None
    series_slug: str | None = None
    info_knowability_regime: str | None = None
    knowable_from: datetime | None = None
    knowability_label_source: str | None = None
    knowability_policy_version: str | None = None
    source_version: str | None = None


@dataclass(frozen=True)
class _MarketAttrs:
    token_outcomes: tuple[tuple[str, str], ...]
    question: str | None
    series_slug: str | None
    info_knowability_regime: str | None
    knowable_from: datetime | None
    knowability_label_source: str | None
    knowability_policy_version: str | None
    source_version: str | None


def _as_dict(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return cast(dict[str, Any], value)
    return {}


def _outcomes_from_row(value: object) -> dict[str, Any]:
    return _as_dict(value)


async def snapshot_at(
    session: AsyncSession,
    *,
    condition_id: str,
    at: datetime,
) -> MarketSnapshot | None:
    repo = MarketsRepository(session)
    row = await repo.latest_at_or_before(condition_id, at)
    if row is None:
        return None
    return MarketSnapshot(
        condition_id=row.condition_id,
        known_at=row.known_at,
        token_outcomes=_outcomes_from_row(row.token_outcomes),
        question=row.question,
        series_slug=row.series_slug,
        info_knowability_regime=row.info_knowability_regime,
        knowable_from=row.knowable_from,
        knowability_label_source=row.knowability_label_source,
        knowability_policy_version=row.knowability_policy_version,
        source_version=row.source_version,
    )


def _freeze_outcomes(outcomes: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    items: list[tuple[str, str]] = []
    for key in sorted(outcomes):
        items.append((key, repr(outcomes[key])))
    return tuple(items)


def _attrs(
    *,
    token_outcomes: dict[str, Any],
    question: str | None,
    series_slug: str | None,
    info_knowability_regime: str | None,
    knowable_from: datetime | None,
    knowability_label_source: str | None,
    knowability_policy_version: str | None,
    source_version: str | None,
) -> _MarketAttrs:
    return _MarketAttrs(
        token_outcomes=_freeze_outcomes(token_outcomes),
        question=question,
        series_slug=series_slug,
        info_knowability_regime=info_knowability_regime,
        knowable_from=knowable_from,
        knowability_label_source=knowability_label_source,
        knowability_policy_version=knowability_policy_version,
        source_version=source_version,
    )


def attributes_changed(
    existing: MarketSnapshot,
    *,
    token_outcomes: dict[str, Any],
    question: str | None,
    series_slug: str | None,
    info_knowability_regime: str | None,
    knowable_from: datetime | None,
    knowability_label_source: str | None,
    knowability_policy_version: str | None,
    source_version: str | None,
) -> bool:
    left = _attrs(
        token_outcomes=existing.token_outcomes,
        question=existing.question,
        series_slug=existing.series_slug,
        info_knowability_regime=existing.info_knowability_regime,
        knowable_from=existing.knowable_from,
        knowability_label_source=existing.knowability_label_source,
        knowability_policy_version=existing.knowability_policy_version,
        source_version=existing.source_version,
    )
    right = _attrs(
        token_outcomes=token_outcomes,
        question=question,
        series_slug=series_slug,
        info_knowability_regime=info_knowability_regime,
        knowable_from=knowable_from,
        knowability_label_source=knowability_label_source,
        knowability_policy_version=knowability_policy_version,
        source_version=source_version,
    )
    return left != right


async def append_market_version(
    session: AsyncSession,
    *,
    condition_id: str,
    token_outcomes: dict[str, Any],
    known_at: datetime | None = None,
    question: str | None = None,
    series_slug: str | None = None,
    info_knowability_regime: str | None = None,
    knowable_from: datetime | None = None,
    knowability_label_source: str | None = None,
    knowability_policy_version: str | None = None,
    source_version: str | None = None,
    raw_market_json: object | None = None,
) -> MarketSnapshot | None:
    """Append a markets row only when attributes change. Returns new/latest snapshot."""
    stamp = known_at if known_at is not None else datetime.now(UTC)
    repo = MarketsRepository(session)
    latest = await repo.latest(condition_id)
    if latest is not None:
        current = MarketSnapshot(
            condition_id=latest.condition_id,
            known_at=latest.known_at,
            token_outcomes=_outcomes_from_row(latest.token_outcomes),
            question=latest.question,
            series_slug=latest.series_slug,
            info_knowability_regime=latest.info_knowability_regime,
            knowable_from=latest.knowable_from,
            knowability_label_source=latest.knowability_label_source,
            knowability_policy_version=latest.knowability_policy_version,
            source_version=latest.source_version,
        )
        changed = attributes_changed(
            current,
            token_outcomes=token_outcomes,
            question=question,
            series_slug=series_slug,
            info_knowability_regime=info_knowability_regime,
            knowable_from=knowable_from,
            knowability_label_source=knowability_label_source,
            knowability_policy_version=knowability_policy_version,
            source_version=source_version,
        )
        if not changed:
            return current
    row = await repo.append_version(
        condition_id=condition_id,
        known_at=stamp,
        token_outcomes=token_outcomes,
        question=question,
        series_slug=series_slug,
        info_knowability_regime=info_knowability_regime,
        knowable_from=knowable_from,
        knowability_label_source=knowability_label_source,
        knowability_policy_version=knowability_policy_version,
        source_version=source_version,
        raw_market_json=raw_market_json,
    )
    return MarketSnapshot(
        condition_id=row.condition_id,
        known_at=row.known_at,
        token_outcomes=_outcomes_from_row(row.token_outcomes),
        question=row.question,
        series_slug=row.series_slug,
        info_knowability_regime=row.info_knowability_regime,
        knowable_from=row.knowable_from,
        knowability_label_source=row.knowability_label_source,
        knowability_policy_version=row.knowability_policy_version,
        source_version=row.source_version,
    )


def parse_token_outcomes(raw: object) -> dict[str, Any]:
    """Build token_id → {outcome, outcome_index} from Gamma market JSON.

    Documented Gamma ``GET /markets`` shape: ``outcomes`` and ``clobTokenIds``
    are JSON-encoded strings, index-aligned. Protocol v2 may leave
    ``clobTokenIds`` null and expose ``positionIds`` as a native string array.
    """
    body = _as_dict(raw)
    if not body:
        return {}
    labels = _json_encoded_list(body.get("outcomes"))
    token_ids = _json_encoded_list(body.get("clobTokenIds"))
    if not token_ids:
        token_ids = _native_string_list(body.get("positionIds"))
    if not token_ids or not labels:
        return {}
    return _zip_token_outcomes(token_ids, labels)


def _json_encoded_list(raw: object) -> list[object]:
    if not isinstance(raw, str):
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return []
    if isinstance(parsed, list):
        return cast(list[object], parsed)
    return []


def _native_string_list(raw: object) -> list[object]:
    if isinstance(raw, list):
        return cast(list[object], raw)
    return []


def _zip_token_outcomes(token_ids: list[object], labels: list[object]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for index, token_id in enumerate(token_ids):
        label: object | None = labels[index] if index < len(labels) else None
        out[str(token_id)] = {"outcome": label, "outcome_index": index}
    return out
