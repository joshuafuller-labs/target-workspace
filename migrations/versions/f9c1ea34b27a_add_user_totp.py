"""add user.totp_secret + totp_enabled (tw-mg1a)

Revision ID: f9c1ea34b27a
Revises: e5fa12b3d9c0
Create Date: 2026-05-18 09:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel  # noqa: F401
from alembic import op

revision: str = "f9c1ea34b27a"
down_revision: str | Sequence[str] | None = "e5fa12b3d9c0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.add_column(sa.Column("totp_secret", sa.String(length=64), nullable=True))
        batch_op.add_column(
            sa.Column(
                "totp_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
        batch_op.add_column(sa.Column("totp_activated_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.drop_column("totp_activated_at")
        batch_op.drop_column("totp_enabled")
        batch_op.drop_column("totp_secret")
