"""add audit_chain_head

Revision ID: b4a9c2d7e8f1
Revises: a9f4d1c2b3e6
Create Date: 2026-06-04 21:55:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel  # noqa: F401
from alembic import op

revision: str = "b4a9c2d7e8f1"  # pragma: allowlist secret
down_revision: str | Sequence[str] | None = "a9f4d1c2b3e6"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_chain_head",
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("peer_id", sa.Uuid(), nullable=False),
        sa.Column("head_hash", sa.String(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"]),
        sa.PrimaryKeyConstraint("workspace_id", "peer_id"),
    )
    op.create_index("ix_audit_chain_head_peer_id", "audit_chain_head", ["peer_id"])


def downgrade() -> None:
    op.drop_index("ix_audit_chain_head_peer_id", table_name="audit_chain_head")
    op.drop_table("audit_chain_head")
