"""Set-once archive collector state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from polymarket_insider_tracker.storage.models import ArchiveCollectorStateModel
from polymarket_insider_tracker.storage.repos import TradeArchiveRepository


class ArchiveStartOverwriteError(RuntimeError):
    """Raised when code attempts to silently change a set ``archive_start_at``."""


class RepairCutoverOverwriteError(RuntimeError):
    """Raised when code attempts to silently change ``repair_enabled_at``."""


@dataclass(frozen=True)
class CollectorState:
    source_id: str
    archive_start_at: datetime
    raw_retention: bool
    repair_enabled_at: datetime | None = None


def _from_model(existing: ArchiveCollectorStateModel) -> CollectorState:
    return CollectorState(
        source_id=existing.source_id,
        archive_start_at=existing.archive_start_at,
        raw_retention=existing.raw_retention,
        repair_enabled_at=existing.repair_enabled_at,
    )


async def ensure_archive_start(
    session: AsyncSession,
    *,
    source_id: str,
    raw_retention: bool,
    now: datetime | None = None,
) -> CollectorState:
    """Return durable archive_start_at; set once on first successful collection."""
    repo = TradeArchiveRepository(session)
    existing = await repo.get_collector_state(source_id)
    if existing is not None:
        return _from_model(existing)
    stamp = now if now is not None else datetime.now(UTC)
    created = await repo.insert_collector_state(
        source_id=source_id,
        archive_start_at=stamp,
        raw_retention=raw_retention,
    )
    return _from_model(created)


async def ensure_repair_cutover(
    session: AsyncSession,
    *,
    source_id: str,
    now: datetime | None = None,
) -> CollectorState:
    """Set ``repair_enabled_at`` once on first successful repair enable."""
    repo = TradeArchiveRepository(session)
    existing = await repo.get_collector_state(source_id)
    if existing is None:
        raise RepairCutoverOverwriteError(f"no archive_start_at for source {source_id}")
    if existing.repair_enabled_at is not None:
        return _from_model(existing)
    stamp = now if now is not None else datetime.now(UTC)
    updated = await repo.set_repair_enabled_at_once(source_id=source_id, repair_enabled_at=stamp)
    return _from_model(updated)


async def refuse_silent_overwrite(
    session: AsyncSession,
    *,
    source_id: str,
    proposed_start: datetime,
) -> CollectorState:
    """Load existing state and reject a different proposed start time."""
    repo = TradeArchiveRepository(session)
    existing = await repo.get_collector_state(source_id)
    if existing is None:
        raise ArchiveStartOverwriteError(f"no archive_start_at for source {source_id}")
    if existing.archive_start_at != proposed_start:
        raise ArchiveStartOverwriteError(
            f"refusing silent overwrite of archive_start_at for {source_id}"
        )
    return _from_model(existing)
