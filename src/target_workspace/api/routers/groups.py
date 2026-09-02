"""/v1/groups — Workspace groups (sub-org abstraction). tw-icj8.

Per ADR 0015. MVP scope is the schema + endpoint surface; the ACL ladder
(group_member → board access) integrates with tw-liwf hooks when those
land.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session, select

from target_workspace.api.dependencies import db_session, require_token_scope
from target_workspace.api.rbac import require_role
from target_workspace.db.tables import (
    UserTable,
    WorkspaceGroupMemberTable,
    WorkspaceGroupTable,
)

router = APIRouter(prefix="/v1/groups", tags=["groups"])


class GroupCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    expires_at: datetime | None = None


class GroupOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    name: str
    description: str | None
    expires_at: datetime | None


class MemberAdd(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: UUID
    role_in_group: str | None = None


class MemberOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: UUID
    role_in_group: str | None
    joined_at: datetime


def _to_group(row: WorkspaceGroupTable) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "description": row.description,
        "expires_at": row.expires_at,
    }


@router.post("", response_model=GroupOut, status_code=status.HTTP_201_CREATED)
def create_group(
    body: GroupCreate,
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("groups:write")),
) -> dict[str, Any]:
    require_role(user.role, "commander", action="create group")
    row = WorkspaceGroupTable(
        id=uuid4(),
        workspace_id=user.workspace_id,
        name=body.name,
        description=body.description,
        expires_at=body.expires_at,
        created_at=datetime.now(tz=UTC),
    )
    session.add(row)
    session.flush()
    return _to_group(row)


@router.get("", response_model=list[GroupOut])
def list_groups(
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("groups:read")),
) -> list[dict[str, Any]]:
    rows = session.exec(
        select(WorkspaceGroupTable)
        .where(WorkspaceGroupTable.workspace_id == user.workspace_id)
        .where(WorkspaceGroupTable.deleted_at.is_(None)),  # type: ignore[union-attr]
    ).all()
    return [_to_group(r) for r in rows]


@router.post(
    "/{group_id}/members",
    response_model=MemberOut,
    status_code=status.HTTP_201_CREATED,
)
def add_member(
    group_id: UUID,
    body: MemberAdd,
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("groups:write")),
) -> dict[str, Any]:
    require_role(user.role, "commander", action="add group member")
    group = session.get(WorkspaceGroupTable, group_id)
    if group is None or group.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="group not found")
    target_user = session.get(UserTable, body.user_id)
    if target_user is None or target_user.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    existing = session.exec(
        select(WorkspaceGroupMemberTable)
        .where(WorkspaceGroupMemberTable.group_id == group_id)
        .where(WorkspaceGroupMemberTable.user_id == body.user_id),
    ).first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="user already in group",
        )
    row = WorkspaceGroupMemberTable(
        group_id=group_id,
        user_id=body.user_id,
        role_in_group=body.role_in_group,
        joined_at=datetime.now(tz=UTC),
    )
    session.add(row)
    session.flush()
    return {
        "user_id": row.user_id,
        "role_in_group": row.role_in_group,
        "joined_at": row.joined_at,
    }


@router.get("/{group_id}/members", response_model=list[MemberOut])
def list_members(
    group_id: UUID,
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("groups:read")),
) -> list[dict[str, Any]]:
    group = session.get(WorkspaceGroupTable, group_id)
    if group is None or group.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="group not found")
    rows = session.exec(
        select(WorkspaceGroupMemberTable).where(
            WorkspaceGroupMemberTable.group_id == group_id,
        ),
    ).all()
    return [
        {
            "user_id": r.user_id,
            "role_in_group": r.role_in_group,
            "joined_at": r.joined_at,
        }
        for r in rows
    ]


@router.delete(
    "/{group_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_member(
    group_id: UUID,
    user_id: UUID,
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("groups:write")),
) -> None:
    require_role(user.role, "commander", action="remove group member")
    group = session.get(WorkspaceGroupTable, group_id)
    if group is None or group.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="group not found")
    row = session.exec(
        select(WorkspaceGroupMemberTable)
        .where(WorkspaceGroupMemberTable.group_id == group_id)
        .where(WorkspaceGroupMemberTable.user_id == user_id),
    ).first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="member not found")
    session.delete(row)
    session.flush()
