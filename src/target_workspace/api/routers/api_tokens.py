"""/v1/auth/tokens — API tokens for service accounts (tw-sodu).

Long-lived bearer tokens for integrations. Plaintext returned ONCE on
creation; sha256 stored. Bearer auth lives in api/dependencies.py
where current_user transparently accepts an `Authorization: Bearer`
header in addition to the session cookie.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session, select

from target_workspace.api.dependencies import db_session, require_token_scope
from target_workspace.db.tables import ApiTokenTable, UserTable

router = APIRouter(prefix="/v1/auth/tokens", tags=["tokens"])


class TokenCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    scopes: list[str] = Field(default_factory=lambda: ["*"], min_length=1)
    expires_at: datetime | None = None


class TokenCreated(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    name: str
    token: str  # plaintext — shown ONCE
    role: str
    scopes: list[str]
    expires_at: datetime | None
    preview: str


class TokenListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    name: str
    role: str
    scopes: list[str]
    preview: str
    expires_at: datetime | None
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None


def _hash(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def _normalize_scopes(scopes: list[str] | None) -> list[str]:
    if scopes is None:
        return ["*"]
    normalized = sorted({scope.strip() for scope in scopes if scope.strip()})
    return normalized or ["*"]


@router.post("", response_model=TokenCreated, status_code=status.HTTP_201_CREATED)
def create_token(
    body: TokenCreate,
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("tokens:write")),
) -> dict[str, Any]:
    raw = secrets.token_urlsafe(48)
    hashed = _hash(raw)
    preview = raw[:8]
    row = ApiTokenTable(
        id=uuid4(),
        workspace_id=user.workspace_id,
        created_by_user_id=user.id,
        name=body.name,
        token_hash=hashed,
        preview=preview,
        role=user.role,
        scopes=_normalize_scopes(body.scopes),
        expires_at=body.expires_at.replace(tzinfo=None) if body.expires_at else None,
        created_at=datetime.now(tz=UTC),
    )
    session.add(row)
    session.flush()
    return {
        "id": row.id,
        "name": row.name,
        "token": raw,
        "role": row.role,
        "scopes": _normalize_scopes(row.scopes),
        "expires_at": body.expires_at,
        "preview": preview,
    }


@router.get("", response_model=list[TokenListItem])
def list_tokens(
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("tokens:read")),
) -> list[dict[str, Any]]:
    rows = session.exec(
        select(ApiTokenTable)
        .where(ApiTokenTable.workspace_id == user.workspace_id)
        .where(ApiTokenTable.created_by_user_id == user.id),
    ).all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "role": r.role,
            "scopes": _normalize_scopes(r.scopes),
            "preview": r.preview,
            "expires_at": r.expires_at,
            "created_at": r.created_at,
            "last_used_at": r.last_used_at,
            "revoked_at": r.revoked_at,
        }
        for r in rows
    ]


@router.delete("/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_token(
    token_id: UUID,
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("tokens:write")),
) -> None:
    row = session.get(ApiTokenTable, token_id)
    if row is None or row.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="token not found")
    row.revoked_at = datetime.now(tz=UTC)
    session.add(row)
    session.flush()


def verify_bearer_token_with_scopes(
    session: Session,
    raw_token: str,
) -> tuple[UserTable, list[str]] | None:
    """Resolve a bearer token to a user, or None.

    Caller wires this into the auth dependency so requests with a
    valid Authorization header authenticate even without a cookie.
    """
    hashed = _hash(raw_token)
    row = session.exec(
        select(ApiTokenTable).where(ApiTokenTable.token_hash == hashed),
    ).first()
    if row is None or row.revoked_at is not None:
        return None
    if row.expires_at is not None:
        exp = row.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=UTC)
        if exp <= datetime.now(tz=UTC):
            return None
    # Lookup the creator user — the token inherits their identity.
    user = session.get(UserTable, row.created_by_user_id)
    if user is None or not user.enabled or user.deleted_at is not None:
        return None
    row.last_used_at = datetime.now(tz=UTC)
    session.add(row)
    return user, _normalize_scopes(row.scopes)


def verify_bearer_token(session: Session, raw_token: str) -> UserTable | None:
    resolved = verify_bearer_token_with_scopes(session, raw_token)
    if resolved is None:
        return None
    user, _scopes = resolved
    return user
