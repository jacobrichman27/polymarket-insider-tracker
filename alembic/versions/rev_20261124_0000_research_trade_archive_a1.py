"""Research trade archive markets and knowability tables.

Adds versioned ``markets``, knowability caches/overrides, and
``repair_enabled_at`` on ``archive_collector_state``.

Revision ID: 006_research_trade_archive_a1
Revises: 005_research_trade_archive_a0
Create Date: 2026-11-24 00:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "006_research_trade_archive_a1"
down_revision: str | None = "005_research_trade_archive_a0"
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


def upgrade() -> None:
    op.add_column(
        "archive_collector_state",
        sa.Column("repair_enabled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "markets",
        sa.Column("condition_id", sa.Text(), nullable=False),
        sa.Column("known_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("token_outcomes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("question", sa.Text(), nullable=True),
        sa.Column("series_slug", sa.Text(), nullable=True),
        sa.Column("info_knowability_regime", sa.Text(), nullable=True),
        sa.Column("knowable_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("knowability_label_source", sa.Text(), nullable=True),
        sa.Column("knowability_policy_version", sa.Text(), nullable=True),
        sa.Column("source_version", sa.Text(), nullable=True),
        sa.Column("raw_market_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("condition_id", "known_at"),
    )
    op.create_table(
        "knowability_series_cache",
        sa.Column("series_slug", sa.Text(), nullable=False),
        sa.Column("policy_version", sa.Text(), nullable=False),
        sa.Column("known_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("regime", sa.Text(), nullable=False),
        sa.Column("knowable_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("label_source", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("series_slug", "policy_version", "known_at"),
    )
    op.create_index(
        "idx_knowability_series_slug",
        "knowability_series_cache",
        ["series_slug"],
    )
    op.create_table(
        "knowability_template_cache",
        sa.Column("template_id", sa.Text(), nullable=False),
        sa.Column("allowlist_version", sa.Text(), nullable=False),
        sa.Column("known_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("regime", sa.Text(), nullable=False),
        sa.Column("knowable_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("label_source", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("template_id", "allowlist_version", "known_at"),
    )
    op.create_index(
        "idx_knowability_template_id",
        "knowability_template_cache",
        ["template_id"],
    )
    op.create_table(
        "knowability_overrides",
        sa.Column("key_type", sa.Text(), nullable=False),
        sa.Column("key_id", sa.Text(), nullable=False),
        sa.Column("known_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("regime", sa.Text(), nullable=False),
        sa.Column("knowable_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("policy_version", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("key_type", "key_id", "known_at"),
    )
    op.create_index(
        "idx_knowability_override_key",
        "knowability_overrides",
        ["key_type", "key_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_knowability_override_key", table_name="knowability_overrides")
    op.drop_table("knowability_overrides")
    op.drop_index("idx_knowability_template_id", table_name="knowability_template_cache")
    op.drop_table("knowability_template_cache")
    op.drop_index("idx_knowability_series_slug", table_name="knowability_series_cache")
    op.drop_table("knowability_series_cache")
    op.drop_table("markets")
    op.drop_column("archive_collector_state", "repair_enabled_at")
