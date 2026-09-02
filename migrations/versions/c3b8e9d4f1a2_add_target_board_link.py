"""add target_board_link (tw-v8s)

Cross-board target linking schema per ADR 0017. One canonical target
row; a target appears on a board iff a non-tombstoned target_board_link
row exists. column_id + position are per-board.

Revision ID: c3b8e9d4f1a2
Revises: b2af13c8e76d
Create Date: 2026-05-18 08:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel  # noqa: F401
from alembic import op

revision: str = "c3b8e9d4f1a2"
down_revision: str | Sequence[str] | None = "b2af13c8e76d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "target_board_link",
        sa.Column("target_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("board_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("column_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("added_at", sa.DateTime(), nullable=False),
        sa.Column("added_by", sa.Uuid(), nullable=True),
        sa.Column("removed_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="active"),
        sa.PrimaryKeyConstraint("target_id", "board_id"),
    )


def downgrade() -> None:
    op.drop_table("target_board_link")
