"""add user.must_change_password (tw-4exk)

When a commander provisions a user via POST /v1/users, the flag is set
to True. Login still succeeds but the session is gated until the user
POSTs /v1/auth/change-password. Existing users (bootstrap admin)
default to False on backfill.

Revision ID: d4e72ff1a932
Revises: c7a91e22b801
Create Date: 2026-05-18 03:55:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel  # noqa: F401
from alembic import op

revision: str = "d4e72ff1a932"
down_revision: str | Sequence[str] | None = "c7a91e22b801"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "must_change_password",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )


def downgrade() -> None:
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.drop_column("must_change_password")
