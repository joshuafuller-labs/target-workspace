"""add per-resource ACL (tw-liwf)

Data-model hooks for board-level and target-level access control.
Resolution order in check helper: target_acl > board_acl > group >
workspace tier.

Revision ID: b2af13c8e76d
Revises: d7e8a229f0c5
Create Date: 2026-05-18 08:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel  # noqa: F401
from alembic import op

revision: str = "b2af13c8e76d"
down_revision: str | Sequence[str] | None = "d7e8a229f0c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "board_acl",
        sa.Column("board_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("user_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("role_overlay", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("board_id", "user_id"),
    )
    op.create_table(
        "target_acl",
        sa.Column("target_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("user_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("perms", sa.String(length=128), nullable=False),
        sa.PrimaryKeyConstraint("target_id", "user_id"),
    )


def downgrade() -> None:
    op.drop_table("target_acl")
    op.drop_table("board_acl")
