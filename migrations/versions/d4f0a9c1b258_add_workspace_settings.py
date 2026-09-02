"""add workspace settings columns (tw-smc)

brand_name, default_theme, freshness window seconds, correlation radius.

Revision ID: d4f0a9c1b258
Revises: c9af23b6e041
Create Date: 2026-05-18 15:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel  # noqa: F401
from alembic import op

revision: str = "d4f0a9c1b258"
down_revision: str | Sequence[str] | None = "c9af23b6e041"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("workspace", schema=None) as batch_op:
        batch_op.add_column(sa.Column("brand_name", sa.String(length=200), nullable=True))
        batch_op.add_column(
            sa.Column(
                "default_theme",
                sa.String(length=32),
                nullable=False,
                server_default="neutral",
            ),
        )
        batch_op.add_column(
            sa.Column(
                "freshness_active_seconds",
                sa.Integer(),
                nullable=False,
                server_default="15",
            ),
        )
        batch_op.add_column(
            sa.Column(
                "freshness_coasting_seconds",
                sa.Integer(),
                nullable=False,
                server_default="60",
            ),
        )
        batch_op.add_column(
            sa.Column(
                "freshness_stale_seconds",
                sa.Integer(),
                nullable=False,
                server_default="180",
            ),
        )
        batch_op.add_column(
            sa.Column(
                "correlation_radius_m",
                sa.Float(),
                nullable=False,
                server_default="100.0",
            ),
        )


def downgrade() -> None:
    with op.batch_alter_table("workspace", schema=None) as batch_op:
        batch_op.drop_column("correlation_radius_m")
        batch_op.drop_column("freshness_stale_seconds")
        batch_op.drop_column("freshness_coasting_seconds")
        batch_op.drop_column("freshness_active_seconds")
        batch_op.drop_column("default_theme")
        batch_op.drop_column("brand_name")
