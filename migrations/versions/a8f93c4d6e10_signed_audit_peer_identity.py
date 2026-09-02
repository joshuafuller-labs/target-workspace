"""signed audit events + instance identity (tw-16c0)

Adds:
  - audit_event.peer_id (UUID, nullable for backfill; populated by app
    on insert going forward).
  - audit_event.signature (text, base64 ed25519 signature).
  - instance_identity table: id, peer_id (UUID), public_key_pem,
    private_key_pem, created_at.

The instance bootstraps a single row on first run if none exists.

Revision ID: a8f93c4d6e10
Revises: d4e72ff1a932
Create Date: 2026-05-18 04:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel  # noqa: F401
from alembic import op

revision: str = "a8f93c4d6e10"
down_revision: str | Sequence[str] | None = "d4e72ff1a932"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("audit_event", schema=None) as batch_op:
        batch_op.add_column(sa.Column("peer_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("signature", sa.Text(), nullable=True))

    op.create_table(
        "instance_identity",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("peer_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("public_key_pem", sa.Text(), nullable=False),
        sa.Column("private_key_pem", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("instance_identity")
    with op.batch_alter_table("audit_event", schema=None) as batch_op:
        batch_op.drop_column("signature")
        batch_op.drop_column("peer_id")
