"""Per-resource ACL resolution (tw-liwf).

Resolution ladder, strongest first:
  1. target_acl (per-target perms list)
  2. board_acl (per-board role overlay)
  3. group_member (group-mediated role — when tw-icj8 wires this in)
  4. workspace tier (the canonical RBAC role on user.role)

MVP scope ships the helper + tables. Endpoints adopt the helper
incrementally — board.list is the natural first integration point.
"""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from sqlmodel import Session, select

from target_workspace.db.tables import BoardAclTable, TargetAclTable


def resolve_effective_role(
    *,
    workspace_tier: str,
    board_acl: str | None,
    target_acl: str | None,
) -> str:
    """Resolve a user's effective role for a specific resource.

    Strongest grant wins. target_acl is taken AS the effective role
    when present (overrides everything); board_acl overrides workspace
    tier; absence falls through.
    """
    if target_acl:
        return target_acl
    if board_acl:
        return board_acl
    return workspace_tier


def get_board_role(session: Session, *, board_id: UUID, user_id: UUID) -> str | None:
    """Return the role_overlay for (board, user) or None."""
    row = session.exec(
        select(BoardAclTable)
        .where(BoardAclTable.board_id == board_id)
        .where(BoardAclTable.user_id == user_id),
    ).first()
    return row.role_overlay if row else None


def get_target_perms(
    session: Session,
    *,
    target_id: UUID,
    user_id: UUID,
) -> Iterable[str]:
    """Return the perms list for (target, user) or empty."""
    row = session.exec(
        select(TargetAclTable)
        .where(TargetAclTable.target_id == target_id)
        .where(TargetAclTable.user_id == user_id),
    ).first()
    if row is None:
        return []
    return [p.strip() for p in (row.perms or "").split(",") if p.strip()]
