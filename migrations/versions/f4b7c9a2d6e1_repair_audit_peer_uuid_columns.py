"""repair signed-audit peer UUID columns

Revision ID: f4b7c9a2d6e1
Revises: f0a1b2c3d4e5
Create Date: 2026-06-05 14:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f4b7c9a2d6e1"  # pragma: allowlist secret
down_revision: str | Sequence[str] | None = "f0a1b2c3d4e5"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid_using(column: str) -> str:
    return (
        f"CASE WHEN {column} IS NULL THEN NULL "
        f"ELSE regexp_replace({column}::text, "
        "'^([0-9a-fA-F]{8})([0-9a-fA-F]{4})([0-9a-fA-F]{4})"
        "([0-9a-fA-F]{4})([0-9a-fA-F]{12})$', "
        r"'\1-\2-\3-\4-\5')::uuid END"
    )


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            f"ALTER TABLE audit_event ALTER COLUMN peer_id TYPE UUID USING {_uuid_using('peer_id')}"
        )
        op.execute(
            f"ALTER TABLE instance_identity ALTER COLUMN id TYPE UUID USING {_uuid_using('id')}"
        )
        op.execute(
            "ALTER TABLE instance_identity "
            f"ALTER COLUMN peer_id TYPE UUID USING {_uuid_using('peer_id')}"
        )
        return

    with op.batch_alter_table("audit_event", schema=None) as batch_op:
        batch_op.alter_column("peer_id", existing_type=sa.CHAR(32), type_=sa.Uuid())
    with op.batch_alter_table("instance_identity", schema=None) as batch_op:
        batch_op.alter_column("id", existing_type=sa.CHAR(32), type_=sa.Uuid())
        batch_op.alter_column("peer_id", existing_type=sa.CHAR(32), type_=sa.Uuid())


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "ALTER TABLE audit_event ALTER COLUMN peer_id TYPE CHAR(32) "
            "USING replace(peer_id::text, '-', '')"
        )
        op.execute(
            "ALTER TABLE instance_identity ALTER COLUMN id TYPE CHAR(32) "
            "USING replace(id::text, '-', '')"
        )
        op.execute(
            "ALTER TABLE instance_identity ALTER COLUMN peer_id TYPE CHAR(32) "
            "USING replace(peer_id::text, '-', '')"
        )
        return

    with op.batch_alter_table("audit_event", schema=None) as batch_op:
        batch_op.alter_column("peer_id", existing_type=sa.Uuid(), type_=sa.CHAR(32))
    with op.batch_alter_table("instance_identity", schema=None) as batch_op:
        batch_op.alter_column("id", existing_type=sa.Uuid(), type_=sa.CHAR(32))
        batch_op.alter_column("peer_id", existing_type=sa.Uuid(), type_=sa.CHAR(32))
