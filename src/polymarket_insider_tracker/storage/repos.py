"""Repository pattern implementations for data access.

This module provides clean data access abstractions for wallet profiles,
funding transfers, and wallet relationships.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError

from polymarket_insider_tracker.constants import UNRECORDED_DELIVERY_DISPOSITION
from polymarket_insider_tracker.storage.models import (
    ArchiveCollectorStateModel,
    FundingTransferModel,
    IngestGapEventModel,
    KnowabilityOverrideModel,
    KnowabilityQuestionCacheModel,
    KnowabilitySeriesCacheModel,
    KnowabilityTemplateCacheModel,
    MarketVersionModel,
    RiskAssessmentModel,
    TradeModel,
    WalletProfileModel,
    WalletRelationshipModel,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def rows_affected(result: object) -> bool:
    """Whether the DML ``result`` touched at least one row; rejects non-DML results."""
    if not isinstance(result, CursorResult):
        raise TypeError("DML result is not a cursor result")
    return (result.rowcount or 0) > 0


@dataclass
class WalletProfileDTO:
    """Data transfer object for wallet profiles."""

    address: str
    nonce: int
    first_seen_at: datetime | None
    is_fresh: bool
    matic_balance: Decimal | None
    usdc_balance: Decimal | None
    analyzed_at: datetime
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @classmethod
    def from_model(cls, model: WalletProfileModel) -> WalletProfileDTO:
        """Create DTO from SQLAlchemy model."""
        return cls(
            address=model.address,
            nonce=model.nonce,
            first_seen_at=model.first_seen_at,
            is_fresh=model.is_fresh,
            matic_balance=model.matic_balance,
            usdc_balance=model.usdc_balance,
            analyzed_at=model.analyzed_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


@dataclass
class FundingTransferDTO:
    """Data transfer object for funding transfers."""

    from_address: str
    to_address: str
    amount: Decimal
    token: str
    tx_hash: str
    block_number: int
    timestamp: datetime
    created_at: datetime | None = None

    @classmethod
    def from_model(cls, model: FundingTransferModel) -> FundingTransferDTO:
        """Create DTO from SQLAlchemy model."""
        return cls(
            from_address=model.from_address,
            to_address=model.to_address,
            amount=model.amount,
            token=model.token,
            tx_hash=model.tx_hash,
            block_number=model.block_number,
            timestamp=model.timestamp,
            created_at=model.created_at,
        )


@dataclass
class WalletRelationshipDTO:
    """Data transfer object for wallet relationships."""

    wallet_a: str
    wallet_b: str
    relationship_type: str
    confidence: Decimal
    created_at: datetime | None = None

    @classmethod
    def from_model(cls, model: WalletRelationshipModel) -> WalletRelationshipDTO:
        """Create DTO from SQLAlchemy model."""
        return cls(
            wallet_a=model.wallet_a,
            wallet_b=model.wallet_b,
            relationship_type=model.relationship_type,
            confidence=model.confidence,
            created_at=model.created_at,
        )


class WalletRepository:
    """Repository for wallet profile data access.

    Provides CRUD operations for wallet profiles with async support.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with database session.

        Args:
            session: SQLAlchemy async session.
        """
        self.session = session

    async def get_by_address(self, address: str) -> WalletProfileDTO | None:
        """Get wallet profile by address.

        Args:
            address: Wallet address (lowercase).

        Returns:
            WalletProfileDTO if found, None otherwise.
        """
        result = await self.session.execute(
            select(WalletProfileModel).where(WalletProfileModel.address == address.lower())
        )
        model = result.scalar_one_or_none()
        return WalletProfileDTO.from_model(model) if model else None

    async def get_many(self, addresses: list[str]) -> list[WalletProfileDTO]:
        """Get multiple wallet profiles by addresses.

        Args:
            addresses: List of wallet addresses.

        Returns:
            List of WalletProfileDTOs for found addresses.
        """
        normalized = [addr.lower() for addr in addresses]
        result = await self.session.execute(
            select(WalletProfileModel).where(WalletProfileModel.address.in_(normalized))
        )
        return [WalletProfileDTO.from_model(m) for m in result.scalars().all()]

    async def get_fresh_wallets(self, limit: int = 100) -> list[WalletProfileDTO]:
        """Get recent fresh wallets.

        Args:
            limit: Maximum number of results.

        Returns:
            List of WalletProfileDTOs marked as fresh.
        """
        result = await self.session.execute(
            select(WalletProfileModel)
            .where(WalletProfileModel.is_fresh.is_(True))
            .order_by(WalletProfileModel.analyzed_at.desc())
            .limit(limit)
        )
        return [WalletProfileDTO.from_model(m) for m in result.scalars().all()]

    async def upsert(self, dto: WalletProfileDTO) -> WalletProfileDTO:
        """Insert or update wallet profile.

        Args:
            dto: Wallet profile data.

        Returns:
            Updated WalletProfileDTO.
        """
        now = datetime.now(UTC)
        values = {
            "address": dto.address.lower(),
            "nonce": dto.nonce,
            "first_seen_at": dto.first_seen_at,
            "is_fresh": dto.is_fresh,
            "matic_balance": dto.matic_balance,
            "usdc_balance": dto.usdc_balance,
            "analyzed_at": dto.analyzed_at,
            "updated_at": now,
        }

        # Try PostgreSQL upsert first, fall back to SQLite for testing
        try:
            stmt = pg_insert(WalletProfileModel).values(**values, created_at=now)
            stmt = stmt.on_conflict_do_update(
                index_elements=["address"],
                set_={
                    "nonce": stmt.excluded.nonce,
                    "first_seen_at": stmt.excluded.first_seen_at,
                    "is_fresh": stmt.excluded.is_fresh,
                    "matic_balance": stmt.excluded.matic_balance,
                    "usdc_balance": stmt.excluded.usdc_balance,
                    "analyzed_at": stmt.excluded.analyzed_at,
                    "updated_at": stmt.excluded.updated_at,
                },
            )
            await self.session.execute(stmt)
        except Exception:
            # Fall back to SQLite upsert for testing
            sqlite_stmt = sqlite_insert(WalletProfileModel).values(**values, created_at=now)
            sqlite_stmt = sqlite_stmt.on_conflict_do_update(
                index_elements=["address"],
                set_={
                    "nonce": sqlite_stmt.excluded.nonce,
                    "first_seen_at": sqlite_stmt.excluded.first_seen_at,
                    "is_fresh": sqlite_stmt.excluded.is_fresh,
                    "matic_balance": sqlite_stmt.excluded.matic_balance,
                    "usdc_balance": sqlite_stmt.excluded.usdc_balance,
                    "analyzed_at": sqlite_stmt.excluded.analyzed_at,
                    "updated_at": sqlite_stmt.excluded.updated_at,
                },
            )
            await self.session.execute(sqlite_stmt)

        await self.session.flush()
        return dto

    async def delete(self, address: str) -> bool:
        """Delete wallet profile by address.

        Args:
            address: Wallet address.

        Returns:
            True if deleted, False if not found.
        """
        result = await self.session.execute(
            delete(WalletProfileModel).where(WalletProfileModel.address == address.lower())
        )
        return rows_affected(result)

    async def mark_stale(self, address: str) -> bool:
        """Mark a wallet profile as stale (soft delete).

        Sets analyzed_at to a very old date to trigger re-analysis.

        Args:
            address: Wallet address.

        Returns:
            True if updated, False if not found.
        """
        stale_time = datetime(2000, 1, 1, tzinfo=UTC)
        result = await self.session.execute(
            update(WalletProfileModel)
            .where(WalletProfileModel.address == address.lower())
            .values(analyzed_at=stale_time, updated_at=datetime.now(UTC))
        )
        return rows_affected(result)


class FundingRepository:
    """Repository for funding transfer data access.

    Provides CRUD operations for funding transfers with async support.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with database session.

        Args:
            session: SQLAlchemy async session.
        """
        self.session = session

    async def get_transfers_to(self, address: str, limit: int = 100) -> list[FundingTransferDTO]:
        """Get transfers to a wallet address.

        Args:
            address: Destination wallet address.
            limit: Maximum number of results.

        Returns:
            List of FundingTransferDTOs ordered by timestamp.
        """
        result = await self.session.execute(
            select(FundingTransferModel)
            .where(FundingTransferModel.to_address == address.lower())
            .order_by(FundingTransferModel.timestamp.asc())
            .limit(limit)
        )
        return [FundingTransferDTO.from_model(m) for m in result.scalars().all()]

    async def get_transfers_from(self, address: str, limit: int = 100) -> list[FundingTransferDTO]:
        """Get transfers from a wallet address.

        Args:
            address: Source wallet address.
            limit: Maximum number of results.

        Returns:
            List of FundingTransferDTOs ordered by timestamp.
        """
        result = await self.session.execute(
            select(FundingTransferModel)
            .where(FundingTransferModel.from_address == address.lower())
            .order_by(FundingTransferModel.timestamp.asc())
            .limit(limit)
        )
        return [FundingTransferDTO.from_model(m) for m in result.scalars().all()]

    async def get_first_transfer_to(self, address: str) -> FundingTransferDTO | None:
        """Get the first transfer to a wallet.

        Args:
            address: Wallet address.

        Returns:
            First FundingTransferDTO if found, None otherwise.
        """
        result = await self.session.execute(
            select(FundingTransferModel)
            .where(FundingTransferModel.to_address == address.lower())
            .order_by(FundingTransferModel.timestamp.asc())
            .limit(1)
        )
        model = result.scalar_one_or_none()
        return FundingTransferDTO.from_model(model) if model else None

    async def get_by_tx_hash(self, tx_hash: str) -> FundingTransferDTO | None:
        """Get transfer by transaction hash.

        Args:
            tx_hash: Transaction hash.

        Returns:
            FundingTransferDTO if found, None otherwise.
        """
        result = await self.session.execute(
            select(FundingTransferModel).where(FundingTransferModel.tx_hash == tx_hash.lower())
        )
        model = result.scalar_one_or_none()
        return FundingTransferDTO.from_model(model) if model else None

    async def insert(self, dto: FundingTransferDTO) -> FundingTransferDTO:
        """Insert a new funding transfer.

        Args:
            dto: Funding transfer data.

        Returns:
            Inserted FundingTransferDTO.

        Raises:
            IntegrityError if tx_hash already exists.
        """
        model = FundingTransferModel(
            from_address=dto.from_address.lower(),
            to_address=dto.to_address.lower(),
            amount=dto.amount,
            token=dto.token,
            tx_hash=dto.tx_hash.lower(),
            block_number=dto.block_number,
            timestamp=dto.timestamp,
        )
        self.session.add(model)
        await self.session.flush()
        return dto

    @staticmethod
    def _is_duplicate_funding_error(error: IntegrityError) -> bool:
        """Match structured SQLite and PostgreSQL unique-violation identifiers."""
        original = error.orig
        return (
            getattr(original, "sqlite_errorcode", None) == sqlite3.SQLITE_CONSTRAINT_UNIQUE
            or getattr(original, "sqlstate", None) == "23505"
            or getattr(original, "pgcode", None) == "23505"
        )

    async def _try_insert_single(self, dto: FundingTransferDTO) -> bool:
        try:
            async with self.session.begin_nested():
                await self.insert(dto)
        except IntegrityError as error:
            if self._is_duplicate_funding_error(error):
                return False
            raise
        return True

    async def insert_many(self, dtos: list[FundingTransferDTO]) -> int:
        """Insert multiple funding transfers.

        Skips duplicates silently.

        Args:
            dtos: List of funding transfer data.

        Returns:
            Number of transfers inserted.
        """
        inserted = 0
        for dto in dtos:
            if await self._try_insert_single(dto):
                inserted += 1
        return inserted


class RelationshipRepository:
    """Repository for wallet relationship data access.

    Provides CRUD operations for wallet relationships with async support.
    """

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with database session.

        Args:
            session: SQLAlchemy async session.
        """
        self.session = session

    async def get_relationships(
        self, wallet: str, relationship_type: str | None = None
    ) -> list[WalletRelationshipDTO]:
        """Get relationships for a wallet.

        Args:
            wallet: Wallet address.
            relationship_type: Optional filter by type.

        Returns:
            List of WalletRelationshipDTOs.
        """
        stmt = select(WalletRelationshipModel).where(
            (WalletRelationshipModel.wallet_a == wallet.lower())
            | (WalletRelationshipModel.wallet_b == wallet.lower())
        )
        if relationship_type:
            stmt = stmt.where(WalletRelationshipModel.relationship_type == relationship_type)

        result = await self.session.execute(stmt)
        return [WalletRelationshipDTO.from_model(m) for m in result.scalars().all()]

    async def get_related_wallets(
        self, wallet: str, relationship_type: str | None = None
    ) -> list[str]:
        """Get addresses of related wallets.

        Args:
            wallet: Wallet address.
            relationship_type: Optional filter by type.

        Returns:
            List of related wallet addresses.
        """
        relationships = await self.get_relationships(wallet, relationship_type)
        related: set[str] = set()
        normalized = wallet.lower()
        for rel in relationships:
            if rel.wallet_a == normalized:
                related.add(rel.wallet_b)
            else:
                related.add(rel.wallet_a)
        return list(related)

    async def upsert(self, dto: WalletRelationshipDTO) -> WalletRelationshipDTO:
        """Insert or update wallet relationship.

        Args:
            dto: Wallet relationship data.

        Returns:
            Updated WalletRelationshipDTO.
        """
        now = datetime.now(UTC)
        values = {
            "wallet_a": dto.wallet_a.lower(),
            "wallet_b": dto.wallet_b.lower(),
            "relationship_type": dto.relationship_type,
            "confidence": dto.confidence,
            "created_at": now,
        }

        # Try PostgreSQL upsert first, fall back to SQLite for testing
        try:
            stmt = pg_insert(WalletRelationshipModel).values(**values)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_wallet_relationship",
                set_={"confidence": stmt.excluded.confidence},
            )
            await self.session.execute(stmt)
        except Exception:
            # Fall back to SQLite upsert for testing
            sqlite_stmt = sqlite_insert(WalletRelationshipModel).values(**values)
            sqlite_stmt = sqlite_stmt.on_conflict_do_update(
                index_elements=["wallet_a", "wallet_b", "relationship_type"],
                set_={"confidence": sqlite_stmt.excluded.confidence},
            )
            await self.session.execute(sqlite_stmt)

        await self.session.flush()
        return dto

    async def delete(self, wallet_a: str, wallet_b: str, relationship_type: str) -> bool:
        """Delete a specific relationship.

        Args:
            wallet_a: First wallet address.
            wallet_b: Second wallet address.
            relationship_type: Type of relationship.

        Returns:
            True if deleted, False if not found.
        """
        result = await self.session.execute(
            delete(WalletRelationshipModel).where(
                WalletRelationshipModel.wallet_a == wallet_a.lower(),
                WalletRelationshipModel.wallet_b == wallet_b.lower(),
                WalletRelationshipModel.relationship_type == relationship_type,
            )
        )
        return rows_affected(result)


@dataclass
class RiskAssessmentDTO:
    """Data transfer object for a persisted risk assessment.

    Captures everything a future backtest needs without going back to
    public APIs: trade identity, score, per-signal confidences, and
    whether the alert was actually delivered.
    """

    assessment_id: str
    trade_id: str
    wallet_address: str
    market_id: str
    asset_id: str | None
    side: str
    outcome: str | None
    outcome_index: int | None
    price: Decimal
    size: Decimal
    notional_usdc: Decimal
    trade_timestamp: datetime
    weighted_score: Decimal
    signals_triggered: int
    fresh_wallet_confidence: Decimal | None
    size_anomaly_confidence: Decimal | None
    is_niche_market: bool | None
    volume_impact: Decimal | None
    book_impact: Decimal | None
    wallet_age_hours: Decimal | None
    should_alert: bool
    threshold_at_eval: Decimal
    # Required so a new row can never be silently mislabeled: only the migration
    # backfill may produce 'legacy-unversioned'.
    scoring_algorithm_version: str
    scoring_config: str | None
    delivery_disposition: str = UNRECORDED_DELIVERY_DISPOSITION
    delivery_channels: str | None = None
    dry_run: bool = False
    volume_available: bool | None = None
    market_daily_volume: Decimal | None = None
    book_depth_available: bool | None = None
    wallet_tx_count: int | None = None
    wallet_age_known: bool | None = None
    created_at: datetime | None = None


class RiskAssessmentRepository:
    """Repository for risk assessment data access."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def insert(self, dto: RiskAssessmentDTO) -> RiskAssessmentDTO:
        """Insert a single assessment. Idempotent on assessment_id collisions."""
        model = RiskAssessmentModel(
            assessment_id=dto.assessment_id,
            trade_id=dto.trade_id,
            wallet_address=dto.wallet_address.lower(),
            market_id=dto.market_id,
            asset_id=dto.asset_id,
            side=dto.side,
            outcome=dto.outcome,
            outcome_index=dto.outcome_index,
            price=dto.price,
            size=dto.size,
            notional_usdc=dto.notional_usdc,
            trade_timestamp=dto.trade_timestamp,
            weighted_score=dto.weighted_score,
            signals_triggered=dto.signals_triggered,
            fresh_wallet_confidence=dto.fresh_wallet_confidence,
            size_anomaly_confidence=dto.size_anomaly_confidence,
            is_niche_market=dto.is_niche_market,
            volume_impact=dto.volume_impact,
            book_impact=dto.book_impact,
            wallet_age_hours=dto.wallet_age_hours,
            should_alert=dto.should_alert,
            threshold_at_eval=dto.threshold_at_eval,
            scoring_algorithm_version=dto.scoring_algorithm_version,
            scoring_config=dto.scoring_config,
            delivery_disposition=dto.delivery_disposition,
            delivery_channels=dto.delivery_channels,
            dry_run=dto.dry_run,
            volume_available=dto.volume_available,
            market_daily_volume=dto.market_daily_volume,
            book_depth_available=dto.book_depth_available,
            wallet_tx_count=dto.wallet_tx_count,
            wallet_age_known=dto.wallet_age_known,
        )
        self.session.add(model)
        await self.session.flush()
        return dto

    async def update_delivery(
        self,
        assessment_id: str,
        *,
        delivery_disposition: str,
        delivery_channels: str | None,
        dry_run: bool,
    ) -> bool:
        """Record the delivery outcome on a pending assessment row.

        Returns True when the row existed and was updated, False when no row
        carries ``assessment_id`` (the caller then falls back to inserting the
        complete assessment).
        """
        result = await self.session.execute(
            update(RiskAssessmentModel)
            .where(RiskAssessmentModel.assessment_id == assessment_id)
            .values(
                delivery_disposition=delivery_disposition,
                delivery_channels=delivery_channels,
                dry_run=dry_run,
            )
        )
        return rows_affected(result)


@dataclass(frozen=True)
class TradeTapeDTO:
    """One research trades-tape row for idempotent insert."""

    trade_ts: datetime
    observation_id: str
    observed_at: datetime
    archive_start_at: datetime
    source_id: str
    transaction_hash: str
    proxy_wallet: str
    condition_id: str
    token_id: str
    outcome: str | None
    outcome_index: int | None
    side: str
    price: Decimal
    size_shares: Decimal
    notional_usdc: Decimal
    source: str
    neg_risk: bool | None
    outcome_repair_status: str
    outcome_repaired: str | None
    outcome_index_repaired: int | None
    receipt_status: str
    info_knowability_regime: str | None
    knowability_label_source: str | None
    raw_row_json: object | None


@dataclass(frozen=True)
class IngestGapEventDTO:
    """Durable gap / write-failure ledger row."""

    source_id: str
    class_: str
    reason: str
    from_time: datetime
    detected_at: datetime
    recorded_at: datetime
    status: str
    to_time: datetime | None = None
    observation_id: str | None = None
    pages_examined: int | None = None
    resolved_at: datetime | None = None
    redis_payload: object | None = None
    detail: object | None = None


@dataclass(frozen=True)
class OutcomeRepairKpiCounts:
    """Post-cutover thin-row counts for repair lag / unrepaired KPIs."""

    thin_post_cutover: int
    not_attempted_past_lag: int
    unrepaired: int


class TradeArchiveRepository:
    """Idempotent trades-tape and gap-ledger persistence."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def trade_values(self, dto: TradeTapeDTO) -> dict[str, object]:
        return {
            "trade_ts": dto.trade_ts,
            "observation_id": dto.observation_id,
            "observed_at": dto.observed_at,
            "archive_start_at": dto.archive_start_at,
            "source_id": dto.source_id,
            "transaction_hash": dto.transaction_hash,
            "proxy_wallet": dto.proxy_wallet,
            "condition_id": dto.condition_id,
            "token_id": dto.token_id,
            "outcome": dto.outcome,
            "outcome_index": dto.outcome_index,
            "side": dto.side,
            "price": dto.price,
            "size_shares": dto.size_shares,
            "notional_usdc": dto.notional_usdc,
            "source": dto.source,
            "neg_risk": dto.neg_risk,
            "outcome_repair_status": dto.outcome_repair_status,
            "outcome_repaired": dto.outcome_repaired,
            "outcome_index_repaired": dto.outcome_index_repaired,
            "receipt_status": dto.receipt_status,
            "info_knowability_regime": dto.info_knowability_regime,
            "knowability_label_source": dto.knowability_label_source,
            "raw_row_json": dto.raw_row_json,
        }

    def _dialect_name(self) -> str:
        return self.session.get_bind().dialect.name

    def trade_insert_stmt(self, values: dict[str, object]) -> Any:
        """Dialect-specific idempotent insert (sqlite vs postgres)."""
        elements = ["trade_ts", "observation_id"]
        if self._dialect_name() == "sqlite":
            return (
                sqlite_insert(TradeModel)
                .values(**values)
                .on_conflict_do_nothing(index_elements=elements)
            )
        return (
            pg_insert(TradeModel).values(**values).on_conflict_do_nothing(index_elements=elements)
        )

    async def insert_trade(self, dto: TradeTapeDTO) -> bool:
        """Insert one tape row. Returns True when a new row was written."""
        result = await self.session.execute(self.trade_insert_stmt(self.trade_values(dto)))
        await self.session.flush()
        return rows_affected(result)

    async def open_write_failure(self, dto: IngestGapEventDTO) -> None:
        """Upsert an open write_failure for ``(source_id, observation_id)``."""
        if dto.observation_id is None:
            return
        existing = await self._open_write_failure_row(dto.source_id, dto.observation_id)
        if existing is not None:
            existing.reason = dto.reason
            existing.detail = dto.detail
            existing.detected_at = dto.detected_at
            await self.session.flush()
            return
        self.session.add(self._gap_model(dto))
        await self.session.flush()

    async def resolve_write_failure(self, source_id: str, observation_id: str) -> None:
        now = datetime.now(UTC)
        result = await self.session.execute(
            update(IngestGapEventModel)
            .where(IngestGapEventModel.source_id == source_id)
            .where(IngestGapEventModel.observation_id == observation_id)
            .where(IngestGapEventModel.class_ == "write_failure")
            .where(IngestGapEventModel.status == "open")
            .values(status="resolved", resolved_at=now)
        )
        rows_affected(result)

    async def abandon_write_failure(
        self, source_id: str, observation_id: str, *, reason: str
    ) -> None:
        now = datetime.now(UTC)
        result = await self.session.execute(
            update(IngestGapEventModel)
            .where(IngestGapEventModel.source_id == source_id)
            .where(IngestGapEventModel.observation_id == observation_id)
            .where(IngestGapEventModel.class_ == "write_failure")
            .where(IngestGapEventModel.status == "open")
            .values(status="abandoned", reason=reason, resolved_at=now)
        )
        rows_affected(result)

    async def mirror_ingest_loss(self, dto: IngestGapEventDTO) -> None:
        """Insert an ingest_loss row; ignore duplicates of the same identity."""
        try:
            async with self.session.begin_nested():
                self.session.add(self._gap_model(dto))
                await self.session.flush()
        except IntegrityError:
            return

    async def get_collector_state(self, source_id: str) -> ArchiveCollectorStateModel | None:
        result = await self.session.execute(
            select(ArchiveCollectorStateModel).where(
                ArchiveCollectorStateModel.source_id == source_id
            )
        )
        return result.scalar_one_or_none()

    async def insert_collector_state(
        self, *, source_id: str, archive_start_at: datetime, raw_retention: bool
    ) -> ArchiveCollectorStateModel:
        model = ArchiveCollectorStateModel(
            source_id=source_id,
            archive_start_at=archive_start_at,
            raw_retention=raw_retention,
            repair_enabled_at=None,
            updated_at=datetime.now(UTC),
        )
        self.session.add(model)
        await self.session.flush()
        return model

    async def set_repair_enabled_at_once(
        self, *, source_id: str, repair_enabled_at: datetime
    ) -> ArchiveCollectorStateModel:
        """Set repair cutover once; no-op overwrite when already set."""
        existing = await self.get_collector_state(source_id)
        if existing is None:
            raise ValueError(f"no collector state for {source_id}")
        if existing.repair_enabled_at is not None:
            return existing
        existing.repair_enabled_at = repair_enabled_at
        existing.updated_at = datetime.now(UTC)
        await self.session.flush()
        return existing

    async def update_outcome_repair(
        self,
        *,
        trade_ts: datetime,
        observation_id: str,
        status: str,
        outcome_repaired: str | None,
        outcome_index_repaired: int | None,
    ) -> bool:
        result = await self.session.execute(
            update(TradeModel)
            .where(TradeModel.trade_ts == trade_ts)
            .where(TradeModel.observation_id == observation_id)
            .values(
                outcome_repair_status=status,
                outcome_repaired=outcome_repaired,
                outcome_index_repaired=outcome_index_repaired,
            )
        )
        return rows_affected(result)

    async def count_outcome_repair_kpi(
        self,
        *,
        cutover: datetime,
        now: datetime,
        lag_seconds: int,
        trailing_hours: int = 24,
    ) -> OutcomeRepairKpiCounts:
        """Count thin post-cutover rows for lag / unrepaired KPI (trailing window)."""
        cutover_utc = _as_utc(cutover)
        now_utc = _as_utc(now)
        window_start = max(cutover_utc, now_utc - timedelta(hours=trailing_hours))
        lag_deadline = now_utc - timedelta(seconds=lag_seconds)
        thin = _thin_api_outcome_clause()
        base = and_(TradeModel.observed_at >= window_start, thin)
        thin_total = await self._count_trades(base)
        past_lag = await self._count_trades(
            and_(
                base,
                TradeModel.outcome_repair_status == "not_attempted",
                TradeModel.observed_at <= lag_deadline,
            )
        )
        unrepaired = await self._count_trades(
            and_(base, TradeModel.outcome_repair_status == "unrepaired")
        )
        return OutcomeRepairKpiCounts(
            thin_post_cutover=thin_total,
            not_attempted_past_lag=past_lag,
            unrepaired=unrepaired,
        )

    async def _count_trades(self, *clauses: Any) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(TradeModel).where(*clauses)
        )
        return int(result.scalar_one())

    async def _open_write_failure_row(
        self, source_id: str, observation_id: str
    ) -> IngestGapEventModel | None:
        result = await self.session.execute(
            select(IngestGapEventModel)
            .where(IngestGapEventModel.source_id == source_id)
            .where(IngestGapEventModel.observation_id == observation_id)
            .where(IngestGapEventModel.class_ == "write_failure")
            .where(IngestGapEventModel.status == "open")
            .order_by(IngestGapEventModel.gap_id.desc())
        )
        return result.scalar_one_or_none()

    @staticmethod
    def _gap_model(dto: IngestGapEventDTO) -> IngestGapEventModel:
        return IngestGapEventModel(
            source_id=dto.source_id,
            class_=dto.class_,
            reason=dto.reason,
            from_time=dto.from_time,
            to_time=dto.to_time,
            observation_id=dto.observation_id,
            pages_examined=dto.pages_examined,
            detected_at=dto.detected_at,
            recorded_at=dto.recorded_at,
            resolved_at=dto.resolved_at,
            status=dto.status,
            redis_payload=dto.redis_payload,
            detail=dto.detail,
        )


def _thin_api_outcome_clause() -> Any:
    return or_(
        TradeModel.outcome_index == 999,
        TradeModel.outcome.is_(None),
        TradeModel.outcome == "",
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class MarketsRepository:
    """Append-on-change markets versions and snapshot reads."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def latest(self, condition_id: str) -> MarketVersionModel | None:
        result = await self.session.execute(
            select(MarketVersionModel)
            .where(MarketVersionModel.condition_id == condition_id)
            .order_by(MarketVersionModel.known_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def latest_at_or_before(
        self, condition_id: str, at: datetime
    ) -> MarketVersionModel | None:
        result = await self.session.execute(
            select(MarketVersionModel)
            .where(MarketVersionModel.condition_id == condition_id)
            .where(MarketVersionModel.known_at <= at)
            .order_by(MarketVersionModel.known_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def append_version(
        self,
        *,
        condition_id: str,
        known_at: datetime,
        token_outcomes: object,
        question: str | None = None,
        series_slug: str | None = None,
        info_knowability_regime: str | None = None,
        knowable_from: datetime | None = None,
        knowability_label_source: str | None = None,
        knowability_policy_version: str | None = None,
        source_version: str | None = None,
        raw_market_json: object | None = None,
    ) -> MarketVersionModel:
        model = MarketVersionModel(
            condition_id=condition_id,
            known_at=known_at,
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
        self.session.add(model)
        await self.session.flush()
        return model


class KnowabilityRepository:
    """Knowability overrides and series/template/question caches."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def latest_override(
        self, *, key_type: str, key_id: str
    ) -> KnowabilityOverrideModel | None:
        result = await self.session.execute(
            select(KnowabilityOverrideModel)
            .where(KnowabilityOverrideModel.key_type == key_type)
            .where(KnowabilityOverrideModel.key_id == key_id)
            .order_by(KnowabilityOverrideModel.known_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def append_override(
        self,
        *,
        key_type: str,
        key_id: str,
        known_at: datetime,
        regime: str,
        policy_version: str,
        knowable_from: datetime | None = None,
        notes: str | None = None,
    ) -> KnowabilityOverrideModel:
        model = KnowabilityOverrideModel(
            key_type=key_type,
            key_id=key_id,
            known_at=known_at,
            regime=regime,
            knowable_from=knowable_from,
            notes=notes,
            policy_version=policy_version,
        )
        self.session.add(model)
        await self.session.flush()
        return model

    async def latest_series_cache(
        self, series_slug: str, policy_version: str
    ) -> KnowabilitySeriesCacheModel | None:
        result = await self.session.execute(
            select(KnowabilitySeriesCacheModel)
            .where(KnowabilitySeriesCacheModel.series_slug == series_slug)
            .where(KnowabilitySeriesCacheModel.policy_version == policy_version)
            .order_by(KnowabilitySeriesCacheModel.known_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def append_series_cache(
        self,
        *,
        series_slug: str,
        policy_version: str,
        regime: str,
        known_at: datetime,
        label_source: str,
        knowable_from: datetime | None = None,
    ) -> KnowabilitySeriesCacheModel:
        model = KnowabilitySeriesCacheModel(
            series_slug=series_slug,
            policy_version=policy_version,
            known_at=known_at,
            regime=regime,
            knowable_from=knowable_from,
            label_source=label_source,
        )
        self.session.add(model)
        await self.session.flush()
        return model

    async def latest_template_cache(
        self, template_id: str, allowlist_version: str
    ) -> KnowabilityTemplateCacheModel | None:
        result = await self.session.execute(
            select(KnowabilityTemplateCacheModel)
            .where(KnowabilityTemplateCacheModel.template_id == template_id)
            .where(KnowabilityTemplateCacheModel.allowlist_version == allowlist_version)
            .order_by(KnowabilityTemplateCacheModel.known_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def append_template_cache(
        self,
        *,
        template_id: str,
        allowlist_version: str,
        regime: str,
        known_at: datetime,
        label_source: str,
        knowable_from: datetime | None = None,
    ) -> KnowabilityTemplateCacheModel:
        model = KnowabilityTemplateCacheModel(
            template_id=template_id,
            allowlist_version=allowlist_version,
            known_at=known_at,
            regime=regime,
            knowable_from=knowable_from,
            label_source=label_source,
        )
        self.session.add(model)
        await self.session.flush()
        return model

    async def latest_question_cache(
        self, question_key: str, policy_version: str
    ) -> KnowabilityQuestionCacheModel | None:
        result = await self.session.execute(
            select(KnowabilityQuestionCacheModel)
            .where(KnowabilityQuestionCacheModel.question_key == question_key)
            .where(KnowabilityQuestionCacheModel.policy_version == policy_version)
            .order_by(KnowabilityQuestionCacheModel.known_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def append_question_cache(
        self,
        *,
        question_key: str,
        question_text: str,
        policy_version: str,
        regime: str,
        known_at: datetime,
        label_source: str,
        knowable_from: datetime | None = None,
    ) -> KnowabilityQuestionCacheModel:
        model = KnowabilityQuestionCacheModel(
            question_key=question_key,
            question_text=question_text,
            policy_version=policy_version,
            known_at=known_at,
            regime=regime,
            knowable_from=knowable_from,
            label_source=label_source,
        )
        self.session.add(model)
        await self.session.flush()
        return model
