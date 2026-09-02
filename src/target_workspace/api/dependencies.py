"""FastAPI dependencies — db session, current user."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime

from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlmodel import Session, select

from target_workspace.api.auth import verify_session_full
from target_workspace.api.config import Settings, get_settings
from target_workspace.db import get_engine
from target_workspace.db.tables import UserTable


def db_session() -> Iterator[Session]:
    """Yield a DB session for one request. Commits on success."""
    session = Session(get_engine())
    session.expire_on_commit = False
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def current_user(
    request: Request,
    tw_session: str | None = Cookie(default=None, alias="tw_session"),
    settings: Settings = Depends(get_settings),
    session: Session = Depends(db_session),
) -> UserTable:
    """Resolve the authenticated user from a session cookie OR bearer token.

    Per tw-4exk: when user.must_change_password is True, the user is
    locked out of every route OUTSIDE /v1/auth/* until they POST
    /v1/auth/change-password to clear the flag. /v1/auth/me still works
    (so the SPA can read the flag and render a dialog).

    Per tw-sodu: Authorization: Bearer <api-token> is accepted as an
    alternative to the cookie for service-account integrations.
    """
    # tw-sodu: bearer token takes precedence if present.
    auth_header = request.headers.get("Authorization") or ""
    if auth_header.lower().startswith("bearer "):
        from target_workspace.api.routers.api_tokens import (  # noqa: PLC0415
            verify_bearer_token_with_scopes,
        )

        bearer = auth_header.split(" ", 1)[1].strip()
        resolved = verify_bearer_token_with_scopes(session, bearer)
        if resolved is not None:
            # Bearer tokens skip the must-change-password gate
            # (service accounts don't have password-change UX).
            user, scopes = resolved
            request.state.api_token_scopes = scopes
            return user
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid bearer token",
        )

    if not tw_session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    parsed = verify_session_full(tw_session, settings.session_secret)
    if parsed is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid session")
    user_id, cookie_sv = parsed
    cookie_user = session.exec(select(UserTable).where(UserTable.id == user_id)).first()
    if cookie_user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user not found")
    # tw-ptn2: cookie's embedded session_version must match the live row.
    # Mismatch = the user (or admin) revoked sessions after this cookie
    # was minted.
    if cookie_sv != (cookie_user.session_version or 0):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="session revoked")
    # tw-6to0: time-bound access expiry. Active sessions become invalid
    # once expires_at <= now() — even within /v1/auth/* (don't let an
    # expired user change their password to extend their stay).
    if cookie_user.expires_at is not None:
        exp = cookie_user.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=UTC)
        if exp <= datetime.now(tz=UTC):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="access expired",
            )
    if cookie_user.must_change_password and not request.url.path.startswith("/v1/auth/"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="password change required — POST /v1/auth/change-password to continue",
        )
    return cookie_user


def require_token_scope(scope: str) -> Callable[..., UserTable]:
    def dependency(
        request: Request,
        user: UserTable = Depends(current_user),
    ) -> UserTable:
        scopes = getattr(request.state, "api_token_scopes", None)
        if scopes is None or "*" in scopes or scope in scopes:
            return user
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"missing required token scope: {scope}",
        )

    return dependency


def enforce_token_scope(
    request: Request,
    *accepted_scopes: str,
) -> None:
    scopes = getattr(request.state, "api_token_scopes", None)
    if scopes is None or "*" in scopes:
        return
    for scope in accepted_scopes:
        if scope in scopes:
            return
    required = " or ".join(accepted_scopes)
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"missing required token scope: {required}",
    )


def interactive_user(
    request: Request,
    user: UserTable = Depends(current_user),
) -> UserTable:
    """Require a browser session rather than a bearer API token."""
    if getattr(request.state, "api_token_scopes", None) is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="interactive session required",
        )
    return user
