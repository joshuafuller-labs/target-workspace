"""add ICS positions + assignments (tw-l40z)

Revision ID: c4f9a18b30e2
Revises: b7e2a8c9d106
Create Date: 2026-05-18 10:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel  # noqa: F401
from alembic import op

revision: str = "c4f9a18b30e2"
down_revision: str | Sequence[str] | None = "b7e2a8c9d106"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "position",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("ics_code", sa.String(length=32), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "position_assignment",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("position_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("user_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("op_period_id", sa.Uuid(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("ends_at", sa.DateTime(), nullable=True),
        sa.Column("transferred_from_assignment_id", sa.Uuid(), nullable=True),
        sa.Column("transferred_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("notes", sa.String(length=2000), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("position_assignment")
    op.drop_table("position")
