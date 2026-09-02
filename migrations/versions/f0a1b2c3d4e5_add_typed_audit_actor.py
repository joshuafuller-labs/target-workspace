"""add typed audit actor

Revision ID: f0a1b2c3d4e5
Revises: e6b7c8d9a0f1
Create Date: 2026-06-05 03:35:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f0a1b2c3d4e5"  # pragma: allowlist secret
down_revision: str | Sequence[str] | None = "e6b7c8d9a0f1"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("audit_event", sa.Column("actor_kind", sa.String(), nullable=True))
    op.add_column("audit_event", sa.Column("actor_ref", sa.String(), nullable=True))
    op.add_column(
        "audit_event",
        sa.Column("signature_format_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.execute("UPDATE audit_event SET actor_kind = 'human_user' WHERE actor_kind IS NULL")
    op.create_index("ix_audit_event_actor_kind", "audit_event", ["actor_kind"])
    op.create_index("ix_audit_event_actor_ref", "audit_event", ["actor_ref"])


def downgrade() -> None:
    op.drop_index("ix_audit_event_actor_ref", table_name="audit_event")
    op.drop_index("ix_audit_event_actor_kind", table_name="audit_event")
    op.drop_column("audit_event", "signature_format_version")
    op.drop_column("audit_event", "actor_ref")
    op.drop_column("audit_event", "actor_kind")
