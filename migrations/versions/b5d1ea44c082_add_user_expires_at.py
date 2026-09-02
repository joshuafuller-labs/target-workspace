"""add user.expires_at (tw-6to0)

Time-bound user access. Default NULL (no expiry). When expires_at <= now()
the auth layer rejects login and any subsequent request.

group_member.expires_at is deferred to tw-icj8 (workspace groups ship
together).

Revision ID: b5d1ea44c082
Revises: a8f93c4d6e10
Create Date: 2026-05-18 05:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel  # noqa: F401
from alembic import op

revision: str = "b5d1ea44c082"
down_revision: str | Sequence[str] | None = "a8f93c4d6e10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.add_column(sa.Column("expires_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.drop_column("expires_at")
