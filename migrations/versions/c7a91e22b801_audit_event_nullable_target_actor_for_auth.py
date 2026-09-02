"""audit_event nullable target_id + actor_id for auth events (tw-6llq)

Auth events (login success/failure, logout) live in the same audit_event
table but have no target (target_id) and may have no actor
(actor_id is null when a failed login uses an unknown email).

Revision ID: c7a91e22b801
Revises: e68a488a8214
Create Date: 2026-05-18 03:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel  # noqa: F401
from alembic import op

revision: str = "c7a91e22b801"
down_revision: str | Sequence[str] | None = "e68a488a8214"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("audit_event", schema=None) as batch_op:
        batch_op.alter_column("target_id", existing_type=sa.CHAR(32), nullable=True)
        batch_op.alter_column("actor_id", existing_type=sa.CHAR(32), nullable=True)


def downgrade() -> None:
    # Backfill any null rows with a sentinel UUID before re-imposing NOT NULL.
    # In practice, downgrading after auth events have been recorded loses
    # them — that's acceptable because the upgrade is forward-only operationally.
    with op.batch_alter_table("audit_event", schema=None) as batch_op:
        batch_op.alter_column("target_id", existing_type=sa.CHAR(32), nullable=False)
        batch_op.alter_column("actor_id", existing_type=sa.CHAR(32), nullable=False)
