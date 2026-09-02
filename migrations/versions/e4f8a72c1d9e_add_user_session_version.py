"""add user.session_version (tw-ptn2)

Monotonic counter included in the signed session cookie. Bumping it
invalidates every existing cookie for that user (revoke-all).
Auto-bumped on password change.

Revision ID: e4f8a72c1d9e
Revises: c92e5f88af40
Create Date: 2026-05-18 06:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel  # noqa: F401
from alembic import op

revision: str = "e4f8a72c1d9e"
down_revision: str | Sequence[str] | None = "c92e5f88af40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "session_version",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )


def downgrade() -> None:
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.drop_column("session_version")
