"""add workspace.mfa_required_roles (tw-r1ru)

Workspace-level MFA-enforcement policy: list of role names whose
holders must have totp_enabled before they can be granted that role.

Revision ID: c9af23b6e041
Revises: b8e57c1f3a92
Create Date: 2026-05-18 14:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel  # noqa: F401
from alembic import op

revision: str = "c9af23b6e041"
down_revision: str | Sequence[str] | None = "b8e57c1f3a92"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("workspace", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "mfa_required_roles",
                sa.JSON(),
                nullable=False,
                server_default="[]",
            ),
        )


def downgrade() -> None:
    with op.batch_alter_table("workspace", schema=None) as batch_op:
        batch_op.drop_column("mfa_required_roles")
