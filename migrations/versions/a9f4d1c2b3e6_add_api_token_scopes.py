"""add api_token.scopes (tw-o2t6)

Revision ID: a9f4d1c2b3e6
Revises: c5b8d13e7a44
Create Date: 2026-06-04 19:50:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel  # noqa: F401
from alembic import op

revision: str = "a9f4d1c2b3e6"  # pragma: allowlist secret
down_revision: str | Sequence[str] | None = "c5b8d13e7a44"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("api_token", sa.Column("scopes", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("api_token", "scopes")
