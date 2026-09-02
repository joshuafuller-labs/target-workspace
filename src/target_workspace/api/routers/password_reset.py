"""Password reset flow (tw-qj9k).

POST /v1/auth/forgot-password {email} → 202 always (anti-enumeration).
  If email matches, mints a single-use token, persists sha256 hash,
  sends the plaintext via the pluggable email backend.

POST /v1/auth/reset-password {token, new_password} → 200 on success.
  Validates token, marks used_at, updates password, bumps
  user.session_version (tw-ptn2 — auto-revoke).
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlmodel import Session, select

from target_workspace.api.auth import hash_password, sign_session
from target_workspace.api.config import Settings, get_settings, secure_cookies_for_env
from target_workspace.api.dependencies import db_session
from target_workspace.api.email import get_email_backend
from target_workspace.db.tables import PasswordResetTokenTable, UserTable

router = APIRouter(prefix="/v1/auth", tags=["auth"])


# Knobs: configurable in v1.x via settings.
RESET_TOKEN_TTL_MINUTES = 60


class ForgotPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=8)
    new_password: str = Field(min_length=1, max_length=200)


def _hash(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def _emit_password_event(
    session: Session,
    *,
    workspace_id: UUID,
    actor_id: UUID | None,
    event_type: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Local audit emit — mirrors api.routers.auth._emit_auth_event so
    we don't have a circular import. tw-qj9k touches the password reset
    pipeline; the auth router owns login/logout."""
    from target_workspace.api.signing import sign_audit_event  # noqa: PLC0415
    from target_workspace.api.triggers import (  # noqa: PLC0415
        EmittedAuditEvent,
        fan_out,
    )
    from target_workspace.db.tables import AuditEventTable  # noqa: PLC0415

    row = AuditEventTable(
        workspace_id=workspace_id,
        target_id=None,
        actor_id=actor_id,
        event_type=event_type,
        occurred_at=datetime.now(tz=UTC),
        metadata_json=dict(metadata or {}),
    )
    session.add(row)
    session.flush()
    peer_id, sig, prev_hash = sign_audit_event(
        session,
        event_id=row.id,
        workspace_id=row.workspace_id,
        actor_id=row.actor_id,
        event_type=row.event_type,
        target_id=row.target_id,
        occurred_at=row.occurred_at,
        metadata=row.metadata_json,
    )
    row.peer_id = peer_id
    row.prev_hash = prev_hash
    row.signature = sig
    session.add(row)
    session.flush()
    fan_out(
        EmittedAuditEvent(
            id=row.id,
            workspace_id=row.workspace_id,
            event_type=row.event_type,
            actor_id=row.actor_id,
            target_id=row.target_id,
            occurred_at=row.occurred_at,
            metadata=dict(row.metadata_json),
            peer_id=row.peer_id,
            signature=row.signature,
        ),
    )


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
def forgot_password(
    body: ForgotPasswordRequest,
    request: Request,
    session: Session = Depends(db_session),
) -> dict[str, str]:
    """Anti-enumeration: response is identical regardless of email validity."""
    from target_workspace.api.ratelimit import check_and_record  # noqa: PLC0415

    client_ip = request.client.host if request.client else "unknown"
    allowed, retry = check_and_record(
        bucket="auth.forgot_password.ip",
        key=client_ip,
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="too many requests",
            headers={"Retry-After": str(retry)},
        )

    user = session.exec(select(UserTable).where(UserTable.email == body.email)).first()
    if user is None or user.deleted_at is not None or not user.enabled:
        return {"status": "accepted"}

    raw_token = secrets.token_urlsafe(48)
    hashed = _hash(raw_token)
    expires = datetime.now(tz=UTC) + timedelta(minutes=RESET_TOKEN_TTL_MINUTES)

    row = PasswordResetTokenTable(
        id=uuid4(),
        user_id=user.id,
        token_hash=hashed,
        expires_at=expires.replace(tzinfo=None),
        created_at=datetime.now(tz=UTC),
    )
    session.add(row)

    _emit_password_event(
        session,
        workspace_id=user.workspace_id,
        actor_id=user.id,
        event_type="auth.password.reset.requested",
        metadata={"client_ip": client_ip},
    )
    session.commit()

    backend = get_email_backend()
    # The body intentionally carries the raw token in a token= query
    # parameter form so any UI that parses URLs picks it up. Production
    # deployments should substitute the SPA's reset URL prefix.
    backend.send(
        to=user.email,
        subject="Reset your Target Workspace password",
        body=(
            "Click the link to reset your password.\n\n"
            f"https://workspace.example.invalid/reset?token={raw_token}\n\n"
            "This link is single-use and expires in "
            f"{RESET_TOKEN_TTL_MINUTES} minutes.\n\n"
            "If you didn't request this, you can safely ignore this message."
        ),
    )

    return {"status": "accepted"}


@router.post("/reset-password")
def reset_password(
    body: ResetPasswordRequest,
    response: Response,
    session: Session = Depends(db_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    hashed = _hash(body.token)
    row = session.exec(
        select(PasswordResetTokenTable).where(PasswordResetTokenTable.token_hash == hashed),
    ).first()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="invalid token",
        )
    if row.used_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="token already used",
        )
    expires = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=UTC)
    if expires <= datetime.now(tz=UTC):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="token expired",
        )

    user = session.get(UserTable, row.user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="user not found",
        )

    # tw-fn7a: enforce password policy.
    from target_workspace.api.password_policy import validate_password  # noqa: PLC0415

    validate_password(body.new_password, settings)

    user.password_hash = hash_password(
        body.new_password,
        env=settings.env,
        bcrypt_rounds=settings.bcrypt_rounds,
    )
    user.must_change_password = False
    user.session_version = (user.session_version or 0) + 1  # tw-ptn2 auto-revoke
    # Reset lockout state — a successful reset implies the user wants in.
    user.locked_until = None
    session.add(user)

    row.used_at = datetime.now(tz=UTC)
    session.add(row)

    _emit_password_event(
        session,
        workspace_id=user.workspace_id,
        actor_id=user.id,
        event_type="auth.password.reset.completed",
        metadata={},
    )
    session.commit()
    session.refresh(user)

    # Issue a fresh cookie so the user is logged in immediately.
    token = sign_session(
        user.id,
        settings.session_secret,
        session_version=user.session_version,
    )
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_max_age_seconds,
        httponly=True,
        samesite="lax",
        secure=secure_cookies_for_env(settings.env),
    )
    return {"status": "ok"}
