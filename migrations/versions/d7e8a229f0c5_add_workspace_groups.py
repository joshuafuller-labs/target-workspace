"""add workspace groups (tw-icj8)

Sub-org abstraction per ADR 0015. Tables: group + group_member +
board.owning_group_id slot.

Revision ID: d7e8a229f0c5
Revises: a4c2e88d3f1b
Create Date: 2026-05-18 07:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel  # noqa: F401
from alembic import op

revision: str = "d7e8a229f0c5"
down_revision: str | Sequence[str] | None = "a4c2e88d3f1b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Avoid the reserved word collision: SQLAlchemy quotes it but it's
    # still worth using a less-loaded name. The bd ticket says 'group'
    # — we honour that but it's quoted in DDL.
    op.create_table(
        "workspace_group",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "workspace_group_member",
        sa.Column("group_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("user_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("role_in_group", sa.String(length=64), nullable=True),
        sa.Column("joined_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("group_id", "user_id"),
    )
    with op.batch_alter_table("board", schema=None) as batch_op:
        batch_op.add_column(sa.Column("owning_group_id", sa.Uuid(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("board", schema=None) as batch_op:
        batch_op.drop_column("owning_group_id")
    op.drop_table("workspace_group_member")
    op.drop_table("workspace_group")
