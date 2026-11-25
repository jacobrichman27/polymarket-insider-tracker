"""Durable ingest-loss / write-failure ledger."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from polymarket_insider_tracker.ingestor.observation_boundary import LossEvent
from polymarket_insider_tracker.storage.repos import IngestGapEventDTO, TradeArchiveRepository


def _now() -> datetime:
    return datetime.now(UTC)


def _from_epoch(seconds: int) -> datetime:
    return datetime.fromtimestamp(seconds, tz=UTC)


async def record_write_failure(
    session: AsyncSession,
    *,
    source_id: str,
    observation_id: str,
    reason: str = "archive_insert_failed",
    detail: dict[str, Any] | None = None,
) -> None:
    repo = TradeArchiveRepository(session)
    stamp = _now()
    await repo.open_write_failure(
        IngestGapEventDTO(
            source_id=source_id,
            class_="write_failure",
            reason=reason,
            from_time=stamp,
            detected_at=stamp,
            recorded_at=stamp,
            status="open",
            observation_id=observation_id,
            detail=detail,
        )
    )


async def resolve_write_failure(
    session: AsyncSession, *, source_id: str, observation_id: str
) -> None:
    await TradeArchiveRepository(session).resolve_write_failure(source_id, observation_id)


async def abandon_write_failure(
    session: AsyncSession,
    *,
    source_id: str,
    observation_id: str,
    reason: str = "archive_insert_abandoned",
) -> None:
    await TradeArchiveRepository(session).abandon_write_failure(
        source_id, observation_id, reason=reason
    )


async def mirror_loss_event(session: AsyncSession, *, source_id: str, event: LossEvent) -> None:
    repo = TradeArchiveRepository(session)
    await repo.mirror_ingest_loss(
        IngestGapEventDTO(
            source_id=source_id,
            class_="ingest_loss",
            reason=event.reason.value,
            from_time=_from_epoch(event.from_time),
            to_time=_from_epoch(event.to_time),
            detected_at=_from_epoch(event.detected_at),
            recorded_at=_now(),
            status="open",
            pages_examined=event.pages_examined,
            redis_payload={
                "reason": event.reason.value,
                "from_time": event.from_time,
                "to_time": event.to_time,
                "detected_at": event.detected_at,
                "pages_examined": event.pages_examined,
            },
        )
    )
