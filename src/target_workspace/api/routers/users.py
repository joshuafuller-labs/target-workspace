"""/v1/users — user administration API (tw-41on).

The unblocks-non-dev-admin set. Commanders provision teammates,
disable accounts on an incident, audit who logged in when. Admin
tier additionally can soft-delete users.

Safety gates:
  - cannot delete or disable the last admin (would lock workspace out)
  - creating an admin-tier user requires admin caller (anti-escalation)
  - disabled / deleted users cannot log in (login checks .enabled +
    .deleted_at)
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from target_workspace.api.auth import hash_password
from target_workspace.api.config import Settings, get_settings
from target_workspace.api.dependencies import db_session, require_token_scope
from target_workspace.api.rbac import _TIERS, has_role, require_role
from target_workspace.api.schemas import (
    UserCreate,
    UserListItem,
    UserUpdate,
)
from target_workspace.db.tables import UserTable

router = APIRouter(prefix="/v1/users", tags=["users"])


def _to_item(row: UserTable) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "email": row.email,
        "display_name": row.display_name,
        "role": row.role,
        "enabled": row.enabled,
        "created_at": row.created_at,
        # tw-tl9r: surface TAK callsign on user listings.
        "tak_callsign": row.tak_callsign,
    }


def _is_last_admin(session: Session, user_id: UUID, workspace_id: UUID) -> bool:
    """True if `user_id` is the last enabled, non-deleted admin in the
    workspace. Used by delete + disable to refuse the destructive move."""
    admins = session.exec(
        select(UserTable)
        .where(UserTable.workspace_id == workspace_id)
        .where(UserTable.role == "admin")
        .where(UserTable.enabled)
        .where(UserTable.deleted_at.is_(None)),  # type: ignore[union-attr]
    ).all()
    return len(admins) == 1 and admins[0].id == user_id


@router.post(
    "",
    response_model=UserListItem,
    status_code=status.HTTP_201_CREATED,
)
def create_user(
    body: UserCreate,
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("users:write")),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    require_role(user.role, "commander", action="create user")
    if body.role not in _TIERS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"role must be one of {list(_TIERS)}",
        )
    # Anti-escalation: only admin can mint another admin.
    if body.role == "admin" and not has_role(user.role, "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="only admin can create users with role=admin",
        )

    # tw-fn7a: enforce password policy.
    from target_workspace.api.password_policy import validate_password  # noqa: PLC0415

    validate_password(body.password, settings)

    # Email uniqueness check (the DB has a unique index but we want a
    # clean 409 rather than a 500 on IntegrityError).
    existing = session.exec(
        select(UserTable).where(UserTable.email == body.email),
    ).first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"email {body.email} already exists",
        )

    row = UserTable(
        id=uuid4(),
        workspace_id=user.workspace_id,
        email=body.email,
        display_name=body.display_name,
        role=body.role,
        password_hash=hash_password(
            body.password,
            env=settings.env,
            bcrypt_rounds=settings.bcrypt_rounds,
        ),
        created_at=datetime.now(tz=UTC),
        enabled=True,
        deleted_at=None,
        # tw-4exk: admin-provisioned password is a temp; user must change
        # on first login before any non-/v1/auth route is reachable.
        must_change_password=True,
        # tw-6to0: optional access expiry.
        expires_at=body.expires_at,
    )
    session.add(row)
    session.flush()
    return _to_item(row)


@router.get("", response_model=list[UserListItem])
def list_users(
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("users:read")),
) -> list[dict[str, Any]]:
    require_role(user.role, "viewer", action="list users")
    rows = session.exec(
        select(UserTable)
        .where(UserTable.workspace_id == user.workspace_id)
        .where(UserTable.deleted_at.is_(None)),  # type: ignore[union-attr]
    ).all()
    return [_to_item(r) for r in rows]


@router.get("/{user_id}", response_model=UserListItem)
def get_user(
    user_id: UUID,
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("users:read")),
) -> dict[str, Any]:
    row = session.get(UserTable, user_id)
    if row is None or row.deleted_at is not None or row.workspace_id != user.workspace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="user not found",
        )
    return _to_item(row)


@router.patch("/{user_id}", response_model=UserListItem)
def patch_user(
    user_id: UUID,
    body: UserUpdate,
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("users:write")),
) -> dict[str, Any]:
    require_role(user.role, "commander", action="edit user")
    fields = body.model_dump(exclude_unset=True, exclude_none=True)
    # Allow explicit-null on tak_callsign / expires_at to mean "clear".
    nullable_clears = {"tak_callsign", "expires_at"} & body.model_fields_set
    if not fields and not nullable_clears:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="no fields to update",
        )
    if "role" in fields and fields["role"] not in _TIERS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"role must be one of {list(_TIERS)}",
        )
    if fields.get("role") == "admin" and not has_role(user.role, "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="only admin can promote a user to admin",
        )
    row = session.get(UserTable, user_id)
    if row is None or row.deleted_at is not None or row.workspace_id != user.workspace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="user not found",
        )
    if "display_name" in fields:
        row.display_name = fields["display_name"]
    if "role" in fields:
        # tw-r1ru: enforce per-workspace MFA policy before granting the role.
        from target_workspace.db.tables import WorkspaceTable  # noqa: PLC0415

        ws = session.get(WorkspaceTable, row.workspace_id)
        required = list((ws.mfa_required_roles or []) if ws else [])
        if fields["role"] in required and not row.totp_enabled:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"role '{fields['role']}' requires MFA per workspace "
                    "policy; user must enroll TOTP first"
                ),
            )
        row.role = fields["role"]
    # tw-6to0: model_dump(exclude_unset=True, exclude_none=True) above
    # excludes None, so use model_fields_set for an explicit-set check
    # (lets the caller clear expires_at by passing null).
    if "expires_at" in body.model_fields_set:
        row.expires_at = body.expires_at
    # tw-tl9r: tak_callsign — workspace-scoped uniqueness.
    if "tak_callsign" in body.model_fields_set:
        cs = body.tak_callsign
        if cs is not None:
            # Reject if another user in the same workspace already holds it.
            clash = session.exec(
                select(UserTable)
                .where(UserTable.workspace_id == row.workspace_id)
                .where(UserTable.tak_callsign == cs)
                .where(UserTable.id != row.id),
            ).first()
            if clash is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"tak_callsign '{cs}' already used by another user",
                )
        row.tak_callsign = cs
    session.add(row)
    session.flush()
    return _to_item(row)


@router.post("/{user_id}/disable", response_model=UserListItem)
def disable_user(
    user_id: UUID,
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("users:write")),
) -> dict[str, Any]:
    require_role(user.role, "commander", action="disable user")
    row = session.get(UserTable, user_id)
    if row is None or row.deleted_at is not None or row.workspace_id != user.workspace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="user not found",
        )
    if row.role == "admin" and _is_last_admin(session, user_id, user.workspace_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="cannot disable the last admin (would lock workspace out)",
        )
    row.enabled = False
    session.add(row)
    session.flush()
    return _to_item(row)


@router.post("/{user_id}/enable", response_model=UserListItem)
def enable_user(
    user_id: UUID,
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("users:write")),
) -> dict[str, Any]:
    require_role(user.role, "commander", action="enable user")
    row = session.get(UserTable, user_id)
    if row is None or row.deleted_at is not None or row.workspace_id != user.workspace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="user not found",
        )
    row.enabled = True
    session.add(row)
    session.flush()
    return _to_item(row)


@router.post("/{user_id}/unlock", response_model=UserListItem)
def unlock_user(
    user_id: UUID,
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("users:write")),
) -> dict[str, Any]:
    """Clear lockout from a user. Admin/commander only. tw-gmq7."""
    require_role(user.role, "commander", action="unlock user")
    row = session.get(UserTable, user_id)
    if row is None or row.deleted_at is not None or row.workspace_id != user.workspace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="user not found",
        )
    row.locked_until = None
    session.add(row)
    session.flush()
    return _to_item(row)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(
    user_id: UUID,
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("users:write")),
) -> None:
    require_role(user.role, "admin", action="delete user")
    row = session.get(UserTable, user_id)
    if row is None or row.deleted_at is not None or row.workspace_id != user.workspace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="user not found",
        )
    if row.role == "admin" and _is_last_admin(session, user_id, user.workspace_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="cannot delete the last admin (would lock workspace out)",
        )
    row.deleted_at = datetime.now(tz=UTC)
    row.enabled = False
    session.add(row)
    session.flush()
