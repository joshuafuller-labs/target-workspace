"""add user.locked_until (tw-gmq7)

Account lockout after N failed login attempts. locked_until is set by
the auth layer; admin can clear via POST /v1/users/{id}/unlock.

Revision ID: c92e5f88af40
Revises: b5d1ea44c082
Create Date: 2026-05-18 05:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel  # noqa: F401
from alembic import op

revision: str = "c92e5f88af40"
down_revision: str | Sequence[str] | None = "b5d1ea44c082"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.add_column(sa.Column("locked_until", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.drop_column("locked_until")
