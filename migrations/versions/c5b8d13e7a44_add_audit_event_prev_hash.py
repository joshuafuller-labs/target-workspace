"""add audit_event.prev_hash

Revision ID: c5b8d13e7a44
Revises: c1d2e3f4a5b6
Create Date: 2026-06-04 14:25:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c5b8d13e7a44"  # pragma: allowlist secret
down_revision: str | Sequence[str] | None = "c1d2e3f4a5b6"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("audit_event", schema=None) as batch_op:
        batch_op.add_column(sa.Column("prev_hash", sa.String(), nullable=True))
        batch_op.create_index("ix_audit_event_prev_hash", ["prev_hash"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("audit_event", schema=None) as batch_op:
        batch_op.drop_index("ix_audit_event_prev_hash")
        batch_op.drop_column("prev_hash")
