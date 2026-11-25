"""Idempotent trades-tape writer."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

from sqlalchemy.exc import ProgrammingError
from sqlalchemy.ext.asyncio import AsyncSession

from polymarket_insider_tracker.ingestor.archive.state import CollectorState, ensure_archive_start
from polymarket_insider_tracker.ingestor.trade_rows import OutcomeResolution, TradeObservation
from polymarket_insider_tracker.storage.repos import TradeArchiveRepository, TradeTapeDTO


class ArchiveWriteStatus(StrEnum):
    INSERTED = "inserted"
    DUPLICATE = "duplicate"
    FAILED = "failed"
    PARTITION_MISSING = "partition_missing"


@dataclass(frozen=True)
class ArchiveWriteResult:
    status: ArchiveWriteStatus
    observation_id: str
    detail: str | None = None


class ArchiveMetrics(Protocol):
    def record_insert(self, result: str) -> None: ...

    def record_partition_miss(self) -> None: ...


class NullArchiveMetrics:
    def record_insert(self, result: str) -> None:
        del result
        return None

    def record_partition_miss(self) -> None:
        return None


def _outcome_repair_status(observation: TradeObservation) -> str:
    if observation.outcome_resolution is OutcomeResolution.PROVIDED:
        return "not_needed"
    return "not_attempted"


def _notional(observation: TradeObservation) -> Decimal:
    return observation.event.price * observation.event.size


def _observed_at(observation: TradeObservation) -> datetime:
    if observation.observed_at is not None:
        return observation.observed_at
    return datetime.now(UTC)


def _raw_json(observation: TradeObservation, *, retain: bool) -> object | None:
    if not retain:
        return None
    return dict(observation.raw_row) if observation.raw_row is not None else None


def is_partition_miss(error: ProgrammingError) -> bool:
    """True when Postgres rejects an insert because no matching partition exists."""
    message = str(error.orig if error.orig is not None else error).lower()
    if "no partition" in message:
        return True
    return "partition" in message and "not found" in message


def _to_dto(
    observation: TradeObservation,
    *,
    source_id: str,
    archive_start_at: datetime,
    raw_retention: bool,
) -> TradeTapeDTO:
    event = observation.event
    outcome = event.outcome or None
    outcome_index = event.outcome_index if outcome else None
    return TradeTapeDTO(
        trade_ts=event.timestamp,
        observation_id=observation.identity,
        observed_at=_observed_at(observation),
        archive_start_at=archive_start_at,
        source_id=source_id,
        transaction_hash=event.trade_id,
        proxy_wallet=event.wallet_address,
        condition_id=event.market_id,
        token_id=event.asset_id,
        outcome=outcome,
        outcome_index=outcome_index,
        side=event.side,
        price=event.price,
        size_shares=event.size,
        notional_usdc=_notional(observation),
        source="data-api.trades",
        neg_risk=None,
        outcome_repair_status=_outcome_repair_status(observation),
        outcome_repaired=None,
        outcome_index_repaired=None,
        receipt_status="not_attempted",
        info_knowability_regime="unknown",
        knowability_label_source="unknown",
        raw_row_json=_raw_json(observation, retain=raw_retention),
    )


class ArchiveWriter:
    """Persist admitted observations to the partitioned trades tape."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        source_id: str,
        raw_retention: bool = True,
        metrics: ArchiveMetrics | None = None,
    ) -> None:
        self._session = session
        self._source_id = source_id
        self._raw_retention = raw_retention
        self._metrics = metrics if metrics is not None else NullArchiveMetrics()
        self._repo = TradeArchiveRepository(session)

    async def write(self, observation: TradeObservation) -> ArchiveWriteResult:
        if not observation.identity:
            return ArchiveWriteResult(
                status=ArchiveWriteStatus.FAILED,
                observation_id=observation.identity,
                detail="missing identity",
            )
        state = await ensure_archive_start(
            self._session,
            source_id=self._source_id,
            raw_retention=self._raw_retention,
        )
        return await self._insert(observation, state)

    async def _insert(
        self, observation: TradeObservation, state: CollectorState
    ) -> ArchiveWriteResult:
        dto = _to_dto(
            observation,
            source_id=self._source_id,
            archive_start_at=state.archive_start_at,
            raw_retention=self._raw_retention,
        )
        try:
            inserted = await self._repo.insert_trade(dto)
        except ProgrammingError as error:
            return self._partition_or_fail(observation, error)
        status = ArchiveWriteStatus.INSERTED if inserted else ArchiveWriteStatus.DUPLICATE
        self._metrics.record_insert(status.value)
        return ArchiveWriteResult(status=status, observation_id=observation.identity)

    def _partition_or_fail(
        self, observation: TradeObservation, error: ProgrammingError
    ) -> ArchiveWriteResult:
        if is_partition_miss(error):
            self._metrics.record_partition_miss()
            self._metrics.record_insert(ArchiveWriteStatus.PARTITION_MISSING.value)
            return ArchiveWriteResult(
                status=ArchiveWriteStatus.PARTITION_MISSING,
                observation_id=observation.identity,
                detail="missing partition",
            )
        self._metrics.record_insert(ArchiveWriteStatus.FAILED.value)
        return ArchiveWriteResult(
            status=ArchiveWriteStatus.FAILED,
            observation_id=observation.identity,
            detail=str(error),
        )
