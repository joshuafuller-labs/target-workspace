"""add workflow_trigger (tw-5m91)

Per-board geofence → column-move rule table.

Revision ID: b8e57c1f3a92
Revises: a4e8c12d6b07
Create Date: 2026-05-18 14:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel  # noqa: F401
from alembic import op

revision: str = "b8e57c1f3a92"
down_revision: str | Sequence[str] | None = "a4e8c12d6b07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workflow_trigger",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("board_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("trigger", sa.String(length=64), nullable=False),
        sa.Column("condition", sa.String(length=128), nullable=False),
        sa.Column("action_move_to_column_id", sa.Uuid(), nullable=False),
        sa.Column("justification_template", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("workflow_trigger")
