"""Add knowability question-text cache.

Revision ID: 007_knowability_question_cache
Revises: 006_research_trade_archive_a1
Create Date: 2026-11-25 00:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "007_knowability_question_cache"
down_revision: str | None = "006_research_trade_archive_a1"
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
    op.create_table(
        "knowability_question_cache",
        sa.Column("question_key", sa.Text(), nullable=False),
        sa.Column("policy_version", sa.Text(), nullable=False),
        sa.Column("known_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("regime", sa.Text(), nullable=False),
        sa.Column("knowable_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("label_source", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("question_key", "policy_version", "known_at"),
    )
    op.create_index(
        "idx_knowability_question_key",
        "knowability_question_cache",
        ["question_key"],
    )


def downgrade() -> None:
    op.drop_index("idx_knowability_question_key", table_name="knowability_question_cache")
    op.drop_table("knowability_question_cache")
