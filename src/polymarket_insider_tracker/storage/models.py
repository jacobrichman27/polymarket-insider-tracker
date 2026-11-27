"""SQLAlchemy models for persistent storage.

This module defines the database schema for storing wallet profiles,
funding transfers, and wallet relationships.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    DateTime,
    Index,
    Integer,
    Numeric,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

if TYPE_CHECKING:
    pass


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


class WalletProfileModel(Base):
    """SQLAlchemy model for wallet profiles.

    Stores analyzed wallet information including age, transaction count,
    balances, and freshness classification.
    """

    __tablename__ = "wallet_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    address: Mapped[str] = mapped_column(String(42), unique=True, nullable=False)
    nonce: Mapped[int] = mapped_column(Integer, nullable=False)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_fresh: Mapped[bool] = mapped_column(Boolean, nullable=False)
    matic_balance: Mapped[Decimal | None] = mapped_column(Numeric(30, 0), nullable=True)
    usdc_balance: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    analyzed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (Index("idx_wallet_profiles_address", "address"),)


class FundingTransferModel(Base):
    """SQLAlchemy model for funding transfers.

    Stores ERC20 transfer events to track wallet funding sources.
    """

    __tablename__ = "funding_transfers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    from_address: Mapped[str] = mapped_column(String(42), nullable=False)
    to_address: Mapped[str] = mapped_column(String(42), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(30, 6), nullable=False)
    token: Mapped[str] = mapped_column(String(10), nullable=False)
    tx_hash: Mapped[str] = mapped_column(String(66), unique=True, nullable=False)
    block_number: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        Index("idx_funding_transfers_to", "to_address"),
        Index("idx_funding_transfers_from", "from_address"),
        Index("idx_funding_transfers_block", "block_number"),
    )


class WalletRelationshipModel(Base):
    """SQLAlchemy model for wallet relationships.

    Stores graph edges between wallets representing funding relationships
    or entity linkages.
    """

    __tablename__ = "wallet_relationships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    wallet_a: Mapped[str] = mapped_column(String(42), nullable=False)
    wallet_b: Mapped[str] = mapped_column(String(42), nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(3, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        UniqueConstraint(
            "wallet_a", "wallet_b", "relationship_type", name="uq_wallet_relationship"
        ),
        Index("idx_wallet_relationships_a", "wallet_a"),
        Index("idx_wallet_relationships_b", "wallet_b"),
    )


class RiskAssessmentModel(Base):
    """SQLAlchemy model for risk assessments.

    One row per signal-bearing trade (i.e. trades that triggered at least one
    detector). Captures everything a future backtest needs without going back
    to the public API: trade identity, score, per-signal confidences, and
    whether the alert was actually delivered (could be False due to dedup or
    threshold).
    """

    __tablename__ = "risk_assessments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    assessment_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)

    # Trade identity
    trade_id: Mapped[str] = mapped_column(String(80), nullable=False)
    wallet_address: Mapped[str] = mapped_column(String(42), nullable=False)
    market_id: Mapped[str] = mapped_column(String(80), nullable=False)
    asset_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    outcome: Mapped[str | None] = mapped_column(String(120), nullable=True)
    outcome_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    price: Mapped[Decimal] = mapped_column(Numeric(10, 6), nullable=False)
    size: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    notional_usdc: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    trade_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Scoring
    weighted_score: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)
    signals_triggered: Mapped[int] = mapped_column(Integer, nullable=False)
    fresh_wallet_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    size_anomaly_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    is_niche_market: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    volume_impact: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    book_impact: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    wallet_age_hours: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)

    # Decision
    should_alert: Mapped[bool] = mapped_column(Boolean, nullable=False)
    threshold_at_eval: Mapped[Decimal] = mapped_column(Numeric(4, 3), nullable=False)

    # Scoring reproducibility identity (Patrick's 2026-09-11 schema decision). Every
    # new row records the producing algorithm version and its exact canonical
    # configuration JSON; rows predating the columns are backfilled as
    # 'legacy-unversioned' with NULL config because their configuration is unknowable.
    scoring_algorithm_version: Mapped[str] = mapped_column(String(32), nullable=False)
    scoring_config: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Slice 003 Safe Observable Operation fields
    delivery_disposition: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="unrecorded", default="unrecorded"
    )
    delivery_channels: Mapped[str | None] = mapped_column(Text, nullable=True)
    dry_run: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
    )
    volume_available: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    market_daily_volume: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    book_depth_available: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    wallet_tx_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    wallet_age_known: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        Index("idx_risk_assessments_wallet", "wallet_address"),
        Index("idx_risk_assessments_market", "market_id"),
        Index("idx_risk_assessments_trade_ts", "trade_timestamp"),
        Index("idx_risk_assessments_score", "weighted_score"),
        Index("idx_risk_assessments_disposition", "delivery_disposition"),
    )


class PipelineTerminalErrorModel(Base):
    """Durable record of one terminal pipeline worker failure.

    Written once when the pipeline enters ``PipelineState.ERROR`` from a
    terminal ingestion worker failure. ``/ready`` and ``/health`` read
    through to the newest row, so the terminal reason survives process
    exit. The stored reason is already redacted at the pipeline
    boundary, never a raw secret-bearing string.
    """

    __tablename__ = "pipeline_terminal_errors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    worker: Mapped[str] = mapped_column(String(32), nullable=False, default="trade_poller")
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )

    __table_args__ = (Index("idx_pipeline_terminal_errors_recorded", "recorded_at"),)


class TradeModel(Base):
    """Partitioned research trades-tape row."""

    __tablename__ = "trades"
    __table_args__ = (
        PrimaryKeyConstraint("trade_ts", "observation_id"),
        Index("idx_trades_condition_ts", "condition_id", "trade_ts"),
        Index("idx_trades_wallet_ts", "proxy_wallet", "trade_ts"),
        Index("idx_trades_tx_ts", "transaction_hash", "trade_ts"),
        {"postgresql_partition_by": "RANGE (trade_ts)"},
    )

    trade_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    observation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    archive_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_id: Mapped[str] = mapped_column(Text, nullable=False)
    transaction_hash: Mapped[str] = mapped_column(Text, nullable=False)
    proxy_wallet: Mapped[str] = mapped_column(Text, nullable=False)
    condition_id: Mapped[str] = mapped_column(Text, nullable=False)
    token_id: Mapped[str] = mapped_column(Text, nullable=False)
    outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    side: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(20, 10), nullable=False)
    size_shares: Mapped[Decimal] = mapped_column(Numeric(30, 10), nullable=False)
    notional_usdc: Mapped[Decimal] = mapped_column(Numeric(30, 10), nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    neg_risk: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    outcome_repair_status: Mapped[str] = mapped_column(Text, nullable=False)
    outcome_repaired: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome_index_repaired: Mapped[int | None] = mapped_column(Integer, nullable=True)
    receipt_status: Mapped[str] = mapped_column(Text, nullable=False)
    info_knowability_regime: Mapped[str | None] = mapped_column(Text, nullable=True)
    knowability_label_source: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_row_json: Mapped[object | None] = mapped_column(JSON, nullable=True)
    gamma_enrichment_status: Mapped[str] = mapped_column(
        Text, nullable=False, default="not_attempted"
    )
    funding_lookup_status: Mapped[str] = mapped_column(
        Text, nullable=False, default="not_attempted"
    )
    wallet_hydrate_status: Mapped[str] = mapped_column(
        Text, nullable=False, default="not_attempted"
    )
    block_number: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    log_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    onchain_direction: Mapped[str | None] = mapped_column(Text, nullable=True)
    fee_usdc: Mapped[Decimal | None] = mapped_column(Numeric(30, 10), nullable=True)
    counterparty_wallets: Mapped[object | None] = mapped_column(JSON, nullable=True)
    fill_fingerprint: Mapped[str | None] = mapped_column(Text, nullable=True)
    fingerprint_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    featuring_config_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    featuring_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    enrichment_budget_version: Mapped[str | None] = mapped_column(Text, nullable=True)


class IngestGapEventModel(Base):
    """Durable ingest-loss and archive write-failure ledger."""

    __tablename__ = "ingest_gap_events"
    __table_args__ = (
        Index("idx_ingest_gap_source_class", "source_id", "class"),
        Index("idx_ingest_gap_observation", "observation_id"),
        Index("idx_ingest_gap_status", "status"),
    )

    gap_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(Text, nullable=False)
    class_: Mapped[str] = mapped_column("class", Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    from_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    to_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    observation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pages_examined: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    redis_payload: Mapped[object | None] = mapped_column(JSON, nullable=True)
    detail: Mapped[object | None] = mapped_column(JSON, nullable=True)


class ArchiveCollectorStateModel(Base):
    """Set-once continuous-archive start state per source."""

    __tablename__ = "archive_collector_state"

    source_id: Mapped[str] = mapped_column(Text, primary_key=True)
    archive_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_retention: Mapped[bool] = mapped_column(Boolean, nullable=False)
    repair_enabled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MarketVersionModel(Base):
    """Append-on-change versioned market metadata."""

    __tablename__ = "markets"
    __table_args__ = (PrimaryKeyConstraint("condition_id", "known_at"),)

    condition_id: Mapped[str] = mapped_column(Text, nullable=False)
    known_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    token_outcomes: Mapped[object] = mapped_column(JSON, nullable=False)
    question: Mapped[str | None] = mapped_column(Text, nullable=True)
    series_slug: Mapped[str | None] = mapped_column(Text, nullable=True)
    info_knowability_regime: Mapped[str | None] = mapped_column(Text, nullable=True)
    knowable_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    knowability_label_source: Mapped[str | None] = mapped_column(Text, nullable=True)
    knowability_policy_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    knowability_confidence: Mapped[Decimal | None] = mapped_column(Numeric(4, 3), nullable=True)
    knowability_model_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_market_json: Mapped[object | None] = mapped_column(JSON, nullable=True)


class KnowabilitySeriesCacheModel(Base):
    """Versioned series-slug knowability cache."""

    __tablename__ = "knowability_series_cache"
    __table_args__ = (
        PrimaryKeyConstraint("series_slug", "policy_version", "known_at"),
        Index("idx_knowability_series_slug", "series_slug"),
    )

    series_slug: Mapped[str] = mapped_column(Text, nullable=False)
    policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    known_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    regime: Mapped[str] = mapped_column(Text, nullable=False)
    knowable_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    label_source: Mapped[str] = mapped_column(Text, nullable=False)


class KnowabilityTemplateCacheModel(Base):
    """Versioned allowlisted-template knowability cache."""

    __tablename__ = "knowability_template_cache"
    __table_args__ = (
        PrimaryKeyConstraint("template_id", "allowlist_version", "known_at"),
        Index("idx_knowability_template_id", "template_id"),
    )

    template_id: Mapped[str] = mapped_column(Text, nullable=False)
    allowlist_version: Mapped[str] = mapped_column(Text, nullable=False)
    known_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    regime: Mapped[str] = mapped_column(Text, nullable=False)
    knowable_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    label_source: Mapped[str] = mapped_column(Text, nullable=False)


class KnowabilityQuestionCacheModel(Base):
    """Exact normalized question-text knowability cache (cross condition_id)."""

    __tablename__ = "knowability_question_cache"
    __table_args__ = (
        PrimaryKeyConstraint("question_key", "policy_version", "known_at"),
        Index("idx_knowability_question_key", "question_key"),
    )

    question_key: Mapped[str] = mapped_column(Text, nullable=False)
    policy_version: Mapped[str] = mapped_column(Text, nullable=False)
    known_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    regime: Mapped[str] = mapped_column(Text, nullable=False)
    knowable_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    label_source: Mapped[str] = mapped_column(Text, nullable=False)


class KnowabilityOverrideModel(Base):
    """Append-on-change human knowability overrides."""

    __tablename__ = "knowability_overrides"
    __table_args__ = (
        PrimaryKeyConstraint("key_type", "key_id", "known_at"),
        Index("idx_knowability_override_key", "key_type", "key_id"),
    )

    key_type: Mapped[str] = mapped_column(Text, nullable=False)
    key_id: Mapped[str] = mapped_column(Text, nullable=False)
    known_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    regime: Mapped[str] = mapped_column(Text, nullable=False)
    knowable_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    policy_version: Mapped[str] = mapped_column(Text, nullable=False)


class EnrichmentWorkItemModel(Base):
    """Durable featuring/enrichment work queue row."""

    __tablename__ = "enrichment_work_items"
    __table_args__ = (
        Index("idx_enrichment_work_status", "status"),
        Index("idx_enrichment_work_obs", "observation_id", "trade_ts"),
        UniqueConstraint(
            "observation_id",
            "trade_ts",
            "enrichment_budget_version",
            "trigger",
            name="uq_enrichment_work_obs_budget_trigger",
        ),
    )

    work_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    observation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    trade_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    enrichment_budget_version: Mapped[str] = mapped_column(Text, nullable=False)
    trigger: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    enqueued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class TradeFeaturesModel(Base):
    """Optional featured convenience snapshot (not delayed trade labels)."""

    __tablename__ = "trade_features"
    __table_args__ = (
        PrimaryKeyConstraint(
            "observation_id",
            "trade_ts",
            "feature_version",
            "order_as_of_contract",
        ),
    )

    observation_id: Mapped[str] = mapped_column(String(64), nullable=False)
    trade_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    feature_version: Mapped[str] = mapped_column(Text, nullable=False)
    order_as_of_contract: Mapped[str] = mapped_column(Text, nullable=False)
    enrichment_budget_version: Mapped[str] = mapped_column(Text, nullable=False)
    fingerprint_version: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[object] = mapped_column(JSON, nullable=False)
    materialized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ArchiveWalletModel(Base):
    """Versioned lifetime-hydrate wallet dimension (research archive)."""

    __tablename__ = "wallets"
    __table_args__ = (PrimaryKeyConstraint("proxy_wallet", "known_at"),)

    proxy_wallet: Mapped[str] = mapped_column(Text, nullable=False)
    known_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    wallet_hydrate_status: Mapped[str] = mapped_column(Text, nullable=False)
    lifetime_is_first_trade: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    payload: Mapped[object | None] = mapped_column(JSON, nullable=True)
    event_horizon_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ProxyFundingModel(Base):
    """Versioned proxy funding / owner dimension."""

    __tablename__ = "proxy_funding"
    __table_args__ = (PrimaryKeyConstraint("proxy_wallet", "known_at"),)

    proxy_wallet: Mapped[str] = mapped_column(Text, nullable=False)
    known_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    funding_lookup_status: Mapped[str] = mapped_column(Text, nullable=False)
    funding_source: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    wallet_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    wallet_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    first_funding_exact: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    payload: Mapped[object | None] = mapped_column(JSON, nullable=True)
