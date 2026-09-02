"""add user.tak_callsign (tw-tl9r)

User ↔ TAK callsign mapping for PLI binding. Workspace-scoped unique.

Revision ID: e1ab437c92d5
Revises: d6c2b80f4e91
Create Date: 2026-05-18 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel  # noqa: F401
from alembic import op

revision: str = "e1ab437c92d5"
down_revision: str | Sequence[str] | None = "d6c2b80f4e91"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.add_column(sa.Column("tak_callsign", sa.String(length=32), nullable=True))
    # Workspace-scoped uniqueness. SQLite + alembic batch handles this
    # via the recreate path.
    op.create_index(
        "ix_user_workspace_tak_callsign",
        "user",
        ["workspace_id", "tak_callsign"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_user_workspace_tak_callsign", table_name="user")
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.drop_column("tak_callsign")
