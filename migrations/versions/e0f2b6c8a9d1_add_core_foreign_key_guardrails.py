"""add core foreign key guardrails

Revision ID: e0f2b6c8a9d1
Revises: d4f0a9c1b258
Create Date: 2026-06-04 11:10:00.000000
"""
# ruff: noqa: S608

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "e0f2b6c8a9d1"  # pragma: allowlist secret
down_revision: str | Sequence[str] | None = "d4f0a9c1b258"  # pragma: allowlist secret
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _ident(name: str) -> str:
    return f'"{name}"'


def _text_expr(table: str, column: str) -> str:
    return f"CAST({_ident(table)}.{_ident(column)} AS TEXT)"


def _delete_orphans(table: str, column: str, parent: str, parent_column: str = "id") -> None:
    sql = f"""
        DELETE FROM {_ident(table)}
        WHERE {_ident(column)} IS NOT NULL
          AND NOT EXISTS (
            SELECT 1 FROM {_ident(parent)}
            WHERE {_text_expr(parent, parent_column)} = {_text_expr(table, column)}
          )
        """
    op.execute(sql)


def _null_orphans(table: str, column: str, parent: str, parent_column: str = "id") -> None:
    sql = f"""
        UPDATE {_ident(table)}
        SET {_ident(column)} = NULL
        WHERE {_ident(column)} IS NOT NULL
          AND NOT EXISTS (
            SELECT 1 FROM {_ident(parent)}
            WHERE {_text_expr(parent, parent_column)} = {_text_expr(table, column)}
          )
        """
    op.execute(sql)


def _cleanup_orphans() -> None:
    _null_orphans("board", "owning_group_id", "workspace_group")
    _null_orphans("promotion_policy", "auto_publish_column_id", "column")
    _null_orphans("promotion_policy", "on_low_confidence_route_to_column_id", "column")
    _null_orphans("source_config", "promotion_policy_id", "promotion_policy")
    _null_orphans("audit_event", "from_column_id", "column")
    _null_orphans("audit_event", "to_column_id", "column")
    _null_orphans("target_board_link", "added_by", "user")
    _null_orphans("op_period", "closed_by_user_id", "user")
    _null_orphans("position_assignment", "op_period_id", "op_period")
    _null_orphans("position_assignment", "transferred_from_assignment_id", "position_assignment")
    _null_orphans("position_assignment", "transferred_by_user_id", "user")
    _null_orphans("invitation_token", "group_id", "workspace_group")

    _delete_orphans("workspace_group", "workspace_id", "workspace")
    _delete_orphans("workspace_group_member", "group_id", "workspace_group")
    _delete_orphans("workspace_group_member", "user_id", "user")
    _delete_orphans("board_acl", "board_id", "board")
    _delete_orphans("board_acl", "user_id", "user")
    _delete_orphans("target_acl", "target_id", "target")
    _delete_orphans("target_acl", "user_id", "user")
    _delete_orphans("target_board_link", "target_id", "target")
    _delete_orphans("target_board_link", "board_id", "board")
    _delete_orphans("target_board_link", "column_id", "column")
    _delete_orphans("api_token", "workspace_id", "workspace")
    _delete_orphans("api_token", "created_by_user_id", "user")
    _delete_orphans("password_reset_token", "user_id", "user")
    _delete_orphans("invitation_token", "workspace_id", "workspace")
    _delete_orphans("invitation_token", "issued_by_user_id", "user")
    _delete_orphans("op_period", "board_id", "board")
    _delete_orphans("op_period", "started_by_user_id", "user")
    _delete_orphans("position", "workspace_id", "workspace")
    _delete_orphans("position_assignment", "position_id", "position")
    _delete_orphans("position_assignment", "user_id", "user")
    _delete_orphans("resource", "workspace_id", "workspace")
    _delete_orphans("workflow_trigger", "action_move_to_column_id", "column")


def upgrade() -> None:  # noqa: PLR0915 - explicit FK DDL is clearer than indirection here.
    _cleanup_orphans()

    with op.batch_alter_table("board", schema=None) as batch_op:
        batch_op.create_foreign_key(
            "fk_board_owning_group_id_workspace_group",
            "workspace_group",
            ["owning_group_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("promotion_policy", schema=None) as batch_op:
        batch_op.create_foreign_key(
            "fk_promotion_policy_auto_publish_column_id_column",
            "column",
            ["auto_publish_column_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_promotion_policy_low_confidence_column_id_column",
            "column",
            ["on_low_confidence_route_to_column_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("source_config", schema=None) as batch_op:
        batch_op.create_foreign_key(
            "fk_source_config_promotion_policy_id_promotion_policy",
            "promotion_policy",
            ["promotion_policy_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("audit_event", schema=None) as batch_op:
        batch_op.create_foreign_key(
            "fk_audit_event_from_column_id_column",
            "column",
            ["from_column_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_audit_event_to_column_id_column",
            "column",
            ["to_column_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("workspace_group", schema=None) as batch_op:
        batch_op.create_foreign_key(
            "fk_workspace_group_workspace_id_workspace",
            "workspace",
            ["workspace_id"],
            ["id"],
            ondelete="CASCADE",
        )

    with op.batch_alter_table("workspace_group_member", schema=None) as batch_op:
        batch_op.create_foreign_key(
            "fk_workspace_group_member_group_id_workspace_group",
            "workspace_group",
            ["group_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_foreign_key(
            "fk_workspace_group_member_user_id_user",
            "user",
            ["user_id"],
            ["id"],
            ondelete="CASCADE",
        )

    with op.batch_alter_table("board_acl", schema=None) as batch_op:
        batch_op.create_foreign_key(
            "fk_board_acl_board_id_board",
            "board",
            ["board_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_foreign_key(
            "fk_board_acl_user_id_user",
            "user",
            ["user_id"],
            ["id"],
            ondelete="CASCADE",
        )

    with op.batch_alter_table("target_acl", schema=None) as batch_op:
        batch_op.create_foreign_key(
            "fk_target_acl_target_id_target",
            "target",
            ["target_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_foreign_key(
            "fk_target_acl_user_id_user",
            "user",
            ["user_id"],
            ["id"],
            ondelete="CASCADE",
        )

    with op.batch_alter_table("target_board_link", schema=None) as batch_op:
        batch_op.create_foreign_key(
            "fk_target_board_link_target_id_target",
            "target",
            ["target_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_foreign_key(
            "fk_target_board_link_board_id_board",
            "board",
            ["board_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_foreign_key(
            "fk_target_board_link_column_id_column",
            "column",
            ["column_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_target_board_link_added_by_user",
            "user",
            ["added_by"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("api_token", schema=None) as batch_op:
        batch_op.create_foreign_key(
            "fk_api_token_workspace_id_workspace",
            "workspace",
            ["workspace_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_foreign_key(
            "fk_api_token_created_by_user_id_user",
            "user",
            ["created_by_user_id"],
            ["id"],
        )

    with op.batch_alter_table("password_reset_token", schema=None) as batch_op:
        batch_op.create_foreign_key(
            "fk_password_reset_token_user_id_user",
            "user",
            ["user_id"],
            ["id"],
            ondelete="CASCADE",
        )

    with op.batch_alter_table("invitation_token", schema=None) as batch_op:
        batch_op.create_foreign_key(
            "fk_invitation_token_workspace_id_workspace",
            "workspace",
            ["workspace_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_foreign_key(
            "fk_invitation_token_issued_by_user_id_user",
            "user",
            ["issued_by_user_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_invitation_token_group_id_workspace_group",
            "workspace_group",
            ["group_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("op_period", schema=None) as batch_op:
        batch_op.create_foreign_key(
            "fk_op_period_board_id_board",
            "board",
            ["board_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_op_period_started_by_user_id_user",
            "user",
            ["started_by_user_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_op_period_closed_by_user_id_user",
            "user",
            ["closed_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("position", schema=None) as batch_op:
        batch_op.create_foreign_key(
            "fk_position_workspace_id_workspace",
            "workspace",
            ["workspace_id"],
            ["id"],
            ondelete="CASCADE",
        )

    with op.batch_alter_table("position_assignment", schema=None) as batch_op:
        batch_op.create_foreign_key(
            "fk_position_assignment_position_id_position",
            "position",
            ["position_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_foreign_key(
            "fk_position_assignment_user_id_user",
            "user",
            ["user_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_position_assignment_op_period_id_op_period",
            "op_period",
            ["op_period_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_position_assignment_transferred_from_assignment_id",
            "position_assignment",
            ["transferred_from_assignment_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_position_assignment_transferred_by_user_id_user",
            "user",
            ["transferred_by_user_id"],
            ["id"],
            ondelete="SET NULL",
        )

    with op.batch_alter_table("resource", schema=None) as batch_op:
        batch_op.create_foreign_key(
            "fk_resource_workspace_id_workspace",
            "workspace",
            ["workspace_id"],
            ["id"],
            ondelete="CASCADE",
        )

    with op.batch_alter_table("workflow_trigger", schema=None) as batch_op:
        batch_op.create_foreign_key(
            "fk_workflow_trigger_action_move_to_column_id_column",
            "column",
            ["action_move_to_column_id"],
            ["id"],
            ondelete="CASCADE",
        )


def _drop_constraints(table: str, names: Sequence[str]) -> None:
    with op.batch_alter_table(table, schema=None) as batch_op:
        for name in names:
            batch_op.drop_constraint(name, type_="foreignkey")


def downgrade() -> None:
    _drop_constraints(
        "workflow_trigger",
        ["fk_workflow_trigger_action_move_to_column_id_column"],
    )
    _drop_constraints("resource", ["fk_resource_workspace_id_workspace"])
    _drop_constraints(
        "position_assignment",
        [
            "fk_position_assignment_transferred_by_user_id_user",
            "fk_position_assignment_transferred_from_assignment_id",
            "fk_position_assignment_op_period_id_op_period",
            "fk_position_assignment_user_id_user",
            "fk_position_assignment_position_id_position",
        ],
    )
    _drop_constraints("position", ["fk_position_workspace_id_workspace"])
    _drop_constraints(
        "op_period",
        [
            "fk_op_period_closed_by_user_id_user",
            "fk_op_period_started_by_user_id_user",
            "fk_op_period_board_id_board",
        ],
    )
    _drop_constraints(
        "invitation_token",
        [
            "fk_invitation_token_group_id_workspace_group",
            "fk_invitation_token_issued_by_user_id_user",
            "fk_invitation_token_workspace_id_workspace",
        ],
    )
    _drop_constraints("password_reset_token", ["fk_password_reset_token_user_id_user"])
    _drop_constraints(
        "api_token",
        ["fk_api_token_created_by_user_id_user", "fk_api_token_workspace_id_workspace"],
    )
    _drop_constraints(
        "target_board_link",
        [
            "fk_target_board_link_added_by_user",
            "fk_target_board_link_column_id_column",
            "fk_target_board_link_board_id_board",
            "fk_target_board_link_target_id_target",
        ],
    )
    _drop_constraints(
        "target_acl",
        ["fk_target_acl_user_id_user", "fk_target_acl_target_id_target"],
    )
    _drop_constraints(
        "board_acl",
        ["fk_board_acl_user_id_user", "fk_board_acl_board_id_board"],
    )
    _drop_constraints(
        "workspace_group_member",
        [
            "fk_workspace_group_member_user_id_user",
            "fk_workspace_group_member_group_id_workspace_group",
        ],
    )
    _drop_constraints("workspace_group", ["fk_workspace_group_workspace_id_workspace"])
    _drop_constraints(
        "audit_event",
        ["fk_audit_event_to_column_id_column", "fk_audit_event_from_column_id_column"],
    )
    _drop_constraints(
        "source_config",
        ["fk_source_config_promotion_policy_id_promotion_policy"],
    )
    _drop_constraints(
        "promotion_policy",
        [
            "fk_promotion_policy_low_confidence_column_id_column",
            "fk_promotion_policy_auto_publish_column_id_column",
        ],
    )
    _drop_constraints("board", ["fk_board_owning_group_id_workspace_group"])
