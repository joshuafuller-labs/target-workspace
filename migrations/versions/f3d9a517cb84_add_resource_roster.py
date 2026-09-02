"""add resource_roster (tw-qkp)

ICS-211 check-in roster.

Revision ID: f3d9a517cb84
Revises: e1ab437c92d5
Create Date: 2026-05-18 12:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel  # noqa: F401
from alembic import op

revision: str = "f3d9a517cb84"
down_revision: str | Sequence[str] | None = "e1ab437c92d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "resource",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("callsign", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("certifications", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="checked-in"),
        sa.Column("checked_in_at", sa.DateTime(), nullable=False),
        sa.Column("checked_out_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("resource")
