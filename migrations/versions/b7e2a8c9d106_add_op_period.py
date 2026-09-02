"""add op_period (tw-eebq)

ICS operational period as a first-class concept. Opens via API; closes
either via explicit PATCH or by opening the next period for that board.

Revision ID: b7e2a8c9d106
Revises: f9c1ea34b27a
Create Date: 2026-05-18 10:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel  # noqa: F401
from alembic import op

revision: str = "b7e2a8c9d106"
down_revision: str | Sequence[str] | None = "f9c1ea34b27a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "op_period",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("board_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("ends_at", sa.DateTime(), nullable=True),
        sa.Column("started_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("closed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.Column("iap", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("op_period")
