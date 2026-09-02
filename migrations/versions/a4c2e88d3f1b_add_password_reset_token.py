"""add password_reset_token (tw-qj9k)

Single-use, short-TTL token for password reset. token_hash stored at
rest; plaintext lives only inside the email message body.

Revision ID: a4c2e88d3f1b
Revises: f1d3a91c6b27
Create Date: 2026-05-18 07:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel  # noqa: F401
from alembic import op

revision: str = "a4c2e88d3f1b"
down_revision: str | Sequence[str] | None = "f1d3a91c6b27"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "password_reset_token",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("token_hash", sa.String(length=128), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("used_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("password_reset_token")
