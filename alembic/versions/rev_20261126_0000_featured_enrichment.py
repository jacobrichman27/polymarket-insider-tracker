"""Featured enrichment schema for the research trade archive.

Adds enrichment statuses/locators/fingerprint on ``trades``, plus
``enrichment_work_items``, ``trade_features``, ``wallets``, and ``proxy_funding``.

Revision ID: 008_featured_enrichment
Revises: 007_knowability_question_cache
Create Date: 2026-11-26 00:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "008_featured_enrichment"
down_revision: str | None = "007_knowability_question_cache"
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

_STATUS_DEFAULT = sa.text("'not_attempted'")


def _add_trade_status(name: str) -> None:
    op.add_column(
        "trades",
        sa.Column(name, sa.Text(), nullable=False, server_default=_STATUS_DEFAULT),
    )


def _add_trade_text(name: str) -> None:
    op.add_column("trades", sa.Column(name, sa.Text(), nullable=True))


def _add_trades_enrichment_columns() -> None:
    _add_trade_status("gamma_enrichment_status")
    _add_trade_status("funding_lookup_status")
    _add_trade_status("wallet_hydrate_status")
    op.add_column("trades", sa.Column("block_number", sa.BigInteger(), nullable=True))
    op.add_column("trades", sa.Column("log_index", sa.Integer(), nullable=True))
    _add_trade_text("onchain_direction")
    op.add_column("trades", sa.Column("fee_usdc", sa.Numeric(30, 10), nullable=True))
    op.add_column(
        "trades",
        sa.Column("counterparty_wallets", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    _add_trade_text("fill_fingerprint")
    _add_trade_text("fingerprint_version")
    _add_trade_text("featuring_config_version")
    _add_trade_text("featuring_reason")
    _add_trade_text("enrichment_budget_version")


def _drop_trades_enrichment_columns() -> None:
    for name in (
        "enrichment_budget_version",
        "featuring_reason",
        "featuring_config_version",
        "fingerprint_version",
        "fill_fingerprint",
        "counterparty_wallets",
        "fee_usdc",
        "onchain_direction",
        "log_index",
        "block_number",
        "wallet_hydrate_status",
        "funding_lookup_status",
        "gamma_enrichment_status",
    ):
        op.drop_column("trades", name)


def _create_work_items() -> None:
    op.create_table(
        "enrichment_work_items",
        sa.Column("work_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("observation_id", sa.String(length=64), nullable=False),
        sa.Column("trade_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("enrichment_budget_version", sa.Text(), nullable=False),
        sa.Column("trigger", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("enqueued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("work_id"),
        sa.UniqueConstraint(
            "observation_id",
            "trade_ts",
            "enrichment_budget_version",
            "trigger",
            name="uq_enrichment_work_obs_budget_trigger",
        ),
    )
    op.create_index("idx_enrichment_work_status", "enrichment_work_items", ["status"])
    op.create_index(
        "idx_enrichment_work_obs",
        "enrichment_work_items",
        ["observation_id", "trade_ts"],
    )


def _create_trade_features() -> None:
    op.create_table(
        "trade_features",
        sa.Column("observation_id", sa.String(length=64), nullable=False),
        sa.Column("trade_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("feature_version", sa.Text(), nullable=False),
        sa.Column("order_as_of_contract", sa.Text(), nullable=False),
        sa.Column("enrichment_budget_version", sa.Text(), nullable=False),
        sa.Column("fingerprint_version", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("materialized_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "observation_id",
            "trade_ts",
            "feature_version",
            "order_as_of_contract",
        ),
    )


def _create_wallets() -> None:
    op.create_table(
        "wallets",
        sa.Column("proxy_wallet", sa.Text(), nullable=False),
        sa.Column("known_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("wallet_hydrate_status", sa.Text(), nullable=False),
        sa.Column("lifetime_is_first_trade", sa.Boolean(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("event_horizon_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("proxy_wallet", "known_at"),
    )


def _create_proxy_funding() -> None:
    op.create_table(
        "proxy_funding",
        sa.Column("proxy_wallet", sa.Text(), nullable=False),
        sa.Column("known_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("funding_lookup_status", sa.Text(), nullable=False),
        sa.Column("funding_source", sa.Text(), nullable=True),
        sa.Column("owner_address", sa.Text(), nullable=True),
        sa.Column("wallet_type", sa.Text(), nullable=True),
        sa.Column("wallet_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_funding_exact", sa.Boolean(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("proxy_wallet", "known_at"),
    )


def upgrade() -> None:
    _add_trades_enrichment_columns()
    _create_work_items()
    _create_trade_features()
    _create_wallets()
    _create_proxy_funding()


def downgrade() -> None:
    op.drop_table("proxy_funding")
    op.drop_table("wallets")
    op.drop_table("trade_features")
    op.drop_index("idx_enrichment_work_obs", table_name="enrichment_work_items")
    op.drop_index("idx_enrichment_work_status", table_name="enrichment_work_items")
    op.drop_table("enrichment_work_items")
    _drop_trades_enrichment_columns()
