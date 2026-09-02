"""add column.expected_approving_roles (tw-cck)

Per-column RoE hint: list of role strings that satisfy the approval
gate. SPA renders this as a dropdown on ApprovalPrompt when set.

Revision ID: a4e8c12d6b07
Revises: f3d9a517cb84
Create Date: 2026-05-18 13:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel  # noqa: F401
from alembic import op

revision: str = "a4e8c12d6b07"
down_revision: str | Sequence[str] | None = "f3d9a517cb84"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("column", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "expected_approving_roles",
                sa.JSON(),
                nullable=False,
                server_default="[]",
            ),
        )


def downgrade() -> None:
    with op.batch_alter_table("column", schema=None) as batch_op:
        batch_op.drop_column("expected_approving_roles")
