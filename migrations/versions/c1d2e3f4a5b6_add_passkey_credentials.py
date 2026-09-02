"""add passkey credentials

Revision ID: c1d2e3f4a5b6
Revises: e0f2b6c8a9d1
Create Date: 2026-06-04 11:55:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c1d2e3f4a5b6"  # pragma: allowlist secret
down_revision: str | Sequence[str] | None = "e0f2b6c8a9d1"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "passkey_credential",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("credential_id", sa.String(), nullable=False),
        sa.Column("public_key", sa.String(), nullable=False),
        sa.Column("sign_count", sa.Integer(), nullable=False),
        sa.Column("aaguid", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("passkey_credential", schema=None) as batch_op:
        batch_op.create_index("ix_passkey_credential_user_id", ["user_id"], unique=False)
        batch_op.create_index(
            "ix_passkey_credential_credential_id",
            ["credential_id"],
            unique=True,
        )

    op.create_table(
        "passkey_challenge",
        sa.Column("challenge", sa.String(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("ceremony", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("challenge"),
    )
    with op.batch_alter_table("passkey_challenge", schema=None) as batch_op:
        batch_op.create_index("ix_passkey_challenge_user_id", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_table("passkey_challenge")
    op.drop_table("passkey_credential")
