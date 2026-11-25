"""Research trade archive trades-tape tables.

Adds partitioned ``trades``, durable ``ingest_gap_events``, and
``archive_collector_state``. Pre-creates daily UTC partitions for a
±7-day window around migration time.

Revision ID: 005_research_trade_archive_a0
Revises: 004_terminal_errors
Create Date: 2026-11-20 00:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005_research_trade_archive_a0"
down_revision: str | None = "004_terminal_errors"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

__all__ = [
    "branch_labels",
    "depends_on",
    "down_revision",
    "downgrade",
    "revision",
    "upgrade",
]

_PARTITION_PAST_DAYS = 7
_PARTITION_FUTURE_DAYS = 7


def _utc_today() -> date:
    return datetime.now(UTC).date()


def _day_start(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


def _partition_name(day: date) -> str:
    return f"trades_{day.strftime('%Y%m%d')}"


def _create_daily_partition(day: date) -> None:
    name = _partition_name(day)
    start = _day_start(day).strftime("%Y-%m-%d %H:%M:%S+00")
    end = (_day_start(day) + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S+00")
    # Bounds come only from controlled date arithmetic (never user input).
    op.execute(
        sa.text(
            f"CREATE TABLE IF NOT EXISTS {name} PARTITION OF trades "
            f"FOR VALUES FROM ('{start}') TO ('{end}')"
        )
    )


def _drop_daily_partition(day: date) -> None:
    op.execute(sa.text(f"DROP TABLE IF EXISTS {_partition_name(day)}"))


def _iter_partition_days() -> list[date]:
    today = _utc_today()
    start = today - timedelta(days=_PARTITION_PAST_DAYS)
    count = _PARTITION_PAST_DAYS + _PARTITION_FUTURE_DAYS + 1
    return [start + timedelta(days=offset) for offset in range(count)]


def _create_trades_parent() -> None:
    op.execute(sa.text("""
            CREATE TABLE trades (
                trade_ts TIMESTAMPTZ NOT NULL,
                observation_id VARCHAR(64) NOT NULL,
                observed_at TIMESTAMPTZ NOT NULL,
                archive_start_at TIMESTAMPTZ NOT NULL,
                source_id TEXT NOT NULL,
                transaction_hash TEXT NOT NULL,
                proxy_wallet TEXT NOT NULL,
                condition_id TEXT NOT NULL,
                token_id TEXT NOT NULL,
                outcome TEXT,
                outcome_index INTEGER,
                side TEXT NOT NULL,
                price NUMERIC(20, 10) NOT NULL,
                size_shares NUMERIC(30, 10) NOT NULL,
                notional_usdc NUMERIC(30, 10) NOT NULL,
                source TEXT NOT NULL,
                neg_risk BOOLEAN,
                outcome_repair_status TEXT NOT NULL,
                outcome_repaired TEXT,
                outcome_index_repaired INTEGER,
                receipt_status TEXT NOT NULL,
                info_knowability_regime TEXT,
                knowability_label_source TEXT,
                raw_row_json JSONB,
                PRIMARY KEY (trade_ts, observation_id)
            ) PARTITION BY RANGE (trade_ts)
            """))


def _create_trades_indexes() -> None:
    op.create_index("idx_trades_condition_ts", "trades", ["condition_id", "trade_ts"])
    op.create_index("idx_trades_wallet_ts", "trades", ["proxy_wallet", "trade_ts"])
    op.create_index("idx_trades_tx_ts", "trades", ["transaction_hash", "trade_ts"])


def _create_gap_table() -> None:
    op.create_table(
        "ingest_gap_events",
        sa.Column("gap_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("class", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("from_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("to_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("observation_id", sa.String(length=64), nullable=True),
        sa.Column("pages_examined", sa.Integer(), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("redis_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("detail", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("gap_id"),
    )
    op.create_index(
        "idx_ingest_gap_source_class",
        "ingest_gap_events",
        ["source_id", "class"],
    )
    op.create_index("idx_ingest_gap_observation", "ingest_gap_events", ["observation_id"])
    op.create_index("idx_ingest_gap_status", "ingest_gap_events", ["status"])
    op.execute(sa.text("""
            CREATE UNIQUE INDEX uq_ingest_gap_write_failure_open
            ON ingest_gap_events (source_id, observation_id)
            WHERE class = 'write_failure' AND status = 'open'
            """))
    op.execute(sa.text("""
            CREATE UNIQUE INDEX uq_ingest_gap_ingest_loss_identity
            ON ingest_gap_events (
                source_id, class, reason, from_time, to_time, detected_at
            )
            WHERE class = 'ingest_loss'
            """))


def _create_collector_state() -> None:
    op.create_table(
        "archive_collector_state",
        sa.Column("source_id", sa.Text(), nullable=False),
        sa.Column("archive_start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("raw_retention", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("source_id"),
    )


def upgrade() -> None:
    _create_trades_parent()
    for day in _iter_partition_days():
        _create_daily_partition(day)
    _create_trades_indexes()
    _create_gap_table()
    _create_collector_state()


def downgrade() -> None:
    op.drop_table("archive_collector_state")
    op.execute(sa.text("DROP INDEX IF EXISTS uq_ingest_gap_ingest_loss_identity"))
    op.execute(sa.text("DROP INDEX IF EXISTS uq_ingest_gap_write_failure_open"))
    op.drop_index("idx_ingest_gap_status", table_name="ingest_gap_events")
    op.drop_index("idx_ingest_gap_observation", table_name="ingest_gap_events")
    op.drop_index("idx_ingest_gap_source_class", table_name="ingest_gap_events")
    op.drop_table("ingest_gap_events")
    op.drop_index("idx_trades_tx_ts", table_name="trades")
    op.drop_index("idx_trades_wallet_ts", table_name="trades")
    op.drop_index("idx_trades_condition_ts", table_name="trades")
    for day in _iter_partition_days():
        _drop_daily_partition(day)
    op.execute(sa.text("DROP TABLE IF EXISTS trades"))
