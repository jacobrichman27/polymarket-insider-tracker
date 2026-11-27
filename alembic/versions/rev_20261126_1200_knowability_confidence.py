"""Add knowability confidence and model version on markets.

Revision ID: 009_knowability_confidence
Revises: 008_featured_enrichment
Create Date: 2026-11-26 12:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "009_knowability_confidence"
down_revision: str | None = "008_featured_enrichment"
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
        "markets",
        sa.Column("knowability_confidence", sa.Numeric(4, 3), nullable=True),
    )
    op.add_column(
        "markets",
        sa.Column("knowability_model_version", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("markets", "knowability_model_version")
    op.drop_column("markets", "knowability_confidence")
