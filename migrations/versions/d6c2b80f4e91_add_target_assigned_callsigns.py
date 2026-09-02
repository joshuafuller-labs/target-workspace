"""add target.assigned_callsigns (tw-5kqh)

Revision ID: d6c2b80f4e91
Revises: c4f9a18b30e2
Create Date: 2026-05-18 11:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel  # noqa: F401
from alembic import op

revision: str = "d6c2b80f4e91"
down_revision: str | Sequence[str] | None = "c4f9a18b30e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("target", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "assigned_callsigns",
                sa.JSON(),
                nullable=False,
                server_default="[]",
            ),
        )


def downgrade() -> None:
    with op.batch_alter_table("target", schema=None) as batch_op:
        batch_op.drop_column("assigned_callsigns")
