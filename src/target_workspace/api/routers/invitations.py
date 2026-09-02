"""Invitation flow — coordinator-mintable join tokens (tw-qmnh).

Two surfaces:
  - POST /v1/invitations  (commander+) — issues a token
  - POST /v1/auth/redeem-invitation (anonymous) — creates a user from a token

Token plaintext is shown to the issuer ONCE on creation; we store the
sha256 hash. Default expiry 72h, max_uses 1.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlmodel import Session, select

from target_workspace.api.auth import hash_password, sign_session
from target_workspace.api.config import Settings, get_settings, secure_cookies_for_env
from target_workspace.api.dependencies import db_session, require_token_scope
from target_workspace.api.rbac import require_role
from target_workspace.db.tables import InvitationTokenTable, UserTable

router = APIRouter(tags=["invitations"])


DEFAULT_EXPIRY_HOURS = 72
ROLES_ALLOWED_FOR_INVITE = (
    "viewer",
    "observer",
    "operator",
    "approver",
    "commander",
)


def _hash_token(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


class InvitationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: str = Field(min_length=1)
    expiry_hours: int | None = Field(default=None, ge=1, le=24 * 30)
    max_uses: int | None = Field(default=None, ge=1, le=1000)


class InvitationCreated(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    token: str
    role: str
    expires_at: datetime
    max_uses: int


class InvitationRedeem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=8)
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1, max_length=200)


@router.post(
    "/v1/invitations",
    response_model=InvitationCreated,
    status_code=status.HTTP_201_CREATED,
)
def create_invitation(
    body: InvitationCreate,
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("invitations:write")),
) -> dict[str, Any]:
    require_role(user.role, "commander", action="issue invitation")
    if body.role not in ROLES_ALLOWED_FOR_INVITE:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"role must be one of {list(ROLES_ALLOWED_FOR_INVITE)}",
        )

    raw_token = secrets.token_urlsafe(48)
    hashed = _hash_token(raw_token)
    expiry = datetime.now(tz=UTC) + timedelta(hours=body.expiry_hours or DEFAULT_EXPIRY_HOURS)
    max_uses = body.max_uses or 1

    row = InvitationTokenTable(
        id=uuid4(),
        workspace_id=user.workspace_id,
        issued_by_user_id=user.id,
        token_hash=hashed,
        role=body.role,
        expires_at=expiry.replace(tzinfo=None),
        max_uses=max_uses,
        uses_remaining=max_uses,
        created_at=datetime.now(tz=UTC),
    )
    session.add(row)
    session.flush()
    return {
        "id": row.id,
        "token": raw_token,
        "role": row.role,
        "expires_at": expiry,
        "max_uses": row.max_uses,
    }


# Mounted under /v1/auth so it's exempt from the must-change-password gate
auth_router = APIRouter(prefix="/v1/auth", tags=["invitations"])


@auth_router.post(
    "/redeem-invitation",
    status_code=status.HTTP_201_CREATED,
)
def redeem_invitation(
    body: InvitationRedeem,
    response: Response,
    session: Session = Depends(db_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Create a user from a valid invitation token.

    On success returns the new user + sets a session cookie (so the
    recipient is logged in immediately) AND sets must_change_password=True
    so they're forced through /v1/auth/change-password (tw-4exk).
    """
    hashed = _hash_token(body.token)
    row = session.exec(
        select(InvitationTokenTable).where(InvitationTokenTable.token_hash == hashed),
    ).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="invalid invitation token",
        )
    now = datetime.now(tz=UTC)
    expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=UTC)
    if row.revoked_at is not None or expires <= now or row.uses_remaining <= 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="invitation token spent or expired",
        )

    # tw-fn7a: enforce password policy.
    from target_workspace.api.password_policy import validate_password  # noqa: PLC0415

    validate_password(body.password, settings)

    # Email uniqueness — same as the user-create path.
    existing = session.exec(
        select(UserTable).where(UserTable.email == body.email),
    ).first()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"email {body.email} already exists",
        )

    new_user = UserTable(
        id=uuid4(),
        workspace_id=row.workspace_id,
        email=body.email,
        display_name=body.display_name,
        role=row.role,
        password_hash=hash_password(
            body.password,
            env=settings.env,
            bcrypt_rounds=settings.bcrypt_rounds,
        ),
        created_at=datetime.now(tz=UTC),
        enabled=True,
        deleted_at=None,
        must_change_password=True,  # tw-4exk
    )
    session.add(new_user)
    row.uses_remaining -= 1
    row.last_used_at = datetime.now(tz=UTC)
    session.add(row)
    session.flush()

    # Issue a session cookie so the redeemer is logged in.
    token = sign_session(
        new_user.id,
        settings.session_secret,
        session_version=new_user.session_version,
    )
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_max_age_seconds,
        httponly=True,
        samesite="lax",
        secure=secure_cookies_for_env(settings.env),
    )

    return {
        "id": str(new_user.id),
        "email": new_user.email,
        "display_name": new_user.display_name,
        "role": new_user.role,
        "must_change_password": True,
    }
