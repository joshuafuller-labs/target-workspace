"""add workflow nomination

Revision ID: e6b7c8d9a0f1
Revises: b4a9c2d7e8f1
Create Date: 2026-06-04 22:45:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e6b7c8d9a0f1"  # pragma: allowlist secret
down_revision: str | Sequence[str] | None = "b4a9c2d7e8f1"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workflow_nomination",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("from_column_id", sa.Uuid(), nullable=False),
        sa.Column("to_column_id", sa.Uuid(), nullable=False),
        sa.Column("proposed_by", sa.String(), nullable=False),
        sa.Column("actor_id", sa.Uuid(), nullable=False),
        sa.Column("approver_role", sa.String(), nullable=False),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("resolved_by", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["actor_id"], ["user.id"]),
        sa.ForeignKeyConstraint(["from_column_id"], ["column.id"]),
        sa.ForeignKeyConstraint(["resolved_by"], ["user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["target_id"], ["target.id"]),
        sa.ForeignKeyConstraint(["to_column_id"], ["column.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspace.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workflow_nomination_actor_id", "workflow_nomination", ["actor_id"])
    op.create_index("ix_workflow_nomination_proposed_by", "workflow_nomination", ["proposed_by"])
    op.create_index("ix_workflow_nomination_status", "workflow_nomination", ["status"])
    op.create_index("ix_workflow_nomination_target_id", "workflow_nomination", ["target_id"])
    op.create_index(
        "ix_workflow_nomination_to_column_id",
        "workflow_nomination",
        ["to_column_id"],
    )
    op.create_index(
        "ix_workflow_nomination_workspace_id",
        "workflow_nomination",
        ["workspace_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_workflow_nomination_workspace_id", table_name="workflow_nomination")
    op.drop_index("ix_workflow_nomination_to_column_id", table_name="workflow_nomination")
    op.drop_index("ix_workflow_nomination_target_id", table_name="workflow_nomination")
    op.drop_index("ix_workflow_nomination_status", table_name="workflow_nomination")
    op.drop_index("ix_workflow_nomination_proposed_by", table_name="workflow_nomination")
    op.drop_index("ix_workflow_nomination_actor_id", table_name="workflow_nomination")
    op.drop_table("workflow_nomination")
