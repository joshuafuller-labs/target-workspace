"""/v1/auth — session login / logout."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlmodel import Session, col, select

from target_workspace.api.auth import (
    hash_password,
    sign_session,
    verify_password,
    verify_session,
)
from target_workspace.api.config import Settings, get_settings, secure_cookies_for_env
from target_workspace.api.dependencies import current_user, db_session, interactive_user
from target_workspace.api.schemas import ChangePasswordRequest, LoginRequest, UserOut
from target_workspace.db.tables import AuditEventTable, UserTable, WorkspaceTable

router = APIRouter(prefix="/v1/auth", tags=["auth"])

# tw-gmq7: lockout knobs. Hard-coded at MVP; configurable in v1.x.
LOCKOUT_THRESHOLD = 10
LOCKOUT_WINDOW_MINUTES = 15
LOCKOUT_COOLDOWN_MINUTES = 30

# tw-b3bi: rate-limit bucket for login per source IP.
RATE_LIMIT_BUCKET_LOGIN_IP = "auth.login.ip"


def _emit_auth_event(
    session: Session,
    *,
    workspace_id: UUID,
    actor_id: UUID | None,
    event_type: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Append an auth.* audit event. tw-6llq + tw-16c0.

    Auth events have no target. actor_id may be None (failed login on an
    unknown email — the migration c7a91e22b801 makes both columns nullable).
    Signed at insert via tw-16c0 sign_audit_event. Caller commits.
    """
    from target_workspace.api.signing import sign_audit_event  # noqa: PLC0415

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
    # tw-ngn5: fan out to registered triggers AFTER persistence so a
    # failing trigger can never lose the audit row.
    from target_workspace.api.triggers import (  # noqa: PLC0415
        EmittedAuditEvent,
        fan_out,
    )

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
        )
    )


def _default_workspace_id(session: Session) -> UUID | None:
    """Resolve the single default workspace for un-attributed auth events."""
    row = session.exec(select(WorkspaceTable).order_by(col(WorkspaceTable.created_at))).first()
    return row.id if row else None


def _ua_family(user_agent: str) -> str:
    """Extract a coarse UA family token. Keeps it dep-free.

    Heuristic: pick the first browser-ish keyword present, else the
    leading slash-separated token.
    """
    if not user_agent:
        return "unknown"
    ua_lower = user_agent.lower()
    for needle in (
        "firefox",
        "chrome",
        "safari",
        "edge",
        "opera",
        "curl",
        "wget",
        "python",
        "go-http",
    ):
        if needle in ua_lower:
            return needle
    return user_agent.split("/", 1)[0].lower()


def _detect_suspicious(
    session: Session,
    *,
    user_id: UUID,
    client_ip: str,
    ua_family: str,
) -> list[str]:
    """Return a list of suspicion reasons for this login.

    Looks at past auth.login.success metadata for this user. No prior
    success → 'first_login'. Otherwise, novel IP or novel UA family
    each get flagged.
    """
    rows = session.exec(
        select(AuditEventTable)
        .where(AuditEventTable.actor_id == user_id)
        .where(AuditEventTable.event_type == "auth.login.success"),
    ).all()
    if not rows:
        return ["first_login"]
    seen_ips: set[str] = set()
    seen_uas: set[str] = set()
    for r in rows:
        md = dict(r.metadata_json or {})
        ip = md.get("client_ip")
        ua = md.get("ua_family")
        if ip:
            seen_ips.add(str(ip))
        if ua:
            seen_uas.add(str(ua))
    reasons: list[str] = []
    if client_ip and client_ip not in seen_ips:
        reasons.append("new_ip")
    if ua_family and ua_family not in seen_uas:
        reasons.append("new_user_agent")
    return reasons


@router.post("/login", response_model=UserOut)
def login(  # noqa: PLR0912, PLR0915 — login handles password/lockout/TOTP/session branches; linear flow is auditable
    body: LoginRequest,
    response: Response,
    request: Request,
    session: Session = Depends(db_session),
    settings: Settings = Depends(get_settings),
) -> UserOut:
    from target_workspace.api.ratelimit import check_and_record  # noqa: PLC0415

    # X-Forwarded-For first (typical reverse-proxy deploy); falls back to
    # the socket peer. The proxy is expected to strip the incoming header
    # at the edge and rewrite it — raw trust is intentional for behind-LB
    # deploys.
    xff = request.headers.get("x-forwarded-for")
    if xff:
        client_ip = xff.split(",")[0].strip()
    elif request.client:
        client_ip = request.client.host
    else:
        client_ip = "unknown"

    # tw-b3bi: per-IP rate limit on login. Records before checking
    # credentials so a brute-forcer learns nothing about email validity.
    allowed, retry = check_and_record(bucket=RATE_LIMIT_BUCKET_LOGIN_IP, key=client_ip)
    if not allowed:
        ws_id = _default_workspace_id(session)
        if ws_id is not None:
            _emit_auth_event(
                session,
                workspace_id=ws_id,
                actor_id=None,
                event_type="auth.rate_limited",
                metadata={"client_ip": client_ip, "endpoint": "auth.login"},
            )
            session.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="too many login attempts; try again later",
            headers={"Retry-After": str(retry)},
        )

    user = session.exec(select(UserTable).where(UserTable.email == body.email)).first()

    audit_meta: dict[str, Any] = {"email": body.email}
    if client_ip and client_ip != "unknown":
        audit_meta["client_ip"] = client_ip

    # tw-gmq7: if the account is currently locked, reject before verifying
    # the password — so a brute-forcer learns nothing from the lockout
    # interval. The check uses naive-coerce since SQLite returns naive.
    if user is not None and user.locked_until is not None:
        lu = user.locked_until
        if lu.tzinfo is None:
            lu = lu.replace(tzinfo=UTC)
        if lu > datetime.now(tz=UTC):
            _emit_auth_event(
                session,
                workspace_id=user.workspace_id,
                actor_id=user.id,
                event_type="auth.login.failed",
                metadata={**audit_meta, "reason": "locked"},
            )
            session.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid email or password",
            )

    if user is None or not verify_password(body.password, user.password_hash):
        # Failed login. Record against the user's workspace if email matched,
        # otherwise against the default workspace so the attempt is auditable.
        ws_id = user.workspace_id if user else _default_workspace_id(session)
        if ws_id is not None:
            _emit_auth_event(
                session,
                workspace_id=ws_id,
                actor_id=user.id if user else None,
                event_type="auth.login.failed",
                metadata={**audit_meta, "reason": "invalid_credentials"},
            )
            session.commit()
            # tw-gmq7: if this was a matched user, count recent failures
            # in the rolling window. If we cross the threshold, lock the
            # account and emit auth.account.locked.
            if user is not None:
                window_start = datetime.now(tz=UTC) - timedelta(minutes=LOCKOUT_WINDOW_MINUTES)
                recent_fail_count = session.exec(
                    select(AuditEventTable)
                    .where(AuditEventTable.actor_id == user.id)
                    .where(AuditEventTable.event_type == "auth.login.failed")
                    .where(AuditEventTable.occurred_at >= window_start.replace(tzinfo=None)),
                ).all()
                if len(recent_fail_count) >= LOCKOUT_THRESHOLD:
                    user.locked_until = datetime.now(tz=UTC) + timedelta(
                        minutes=LOCKOUT_COOLDOWN_MINUTES,
                    )
                    session.add(user)
                    _emit_auth_event(
                        session,
                        workspace_id=user.workspace_id,
                        actor_id=user.id,
                        event_type="auth.account.locked",
                        metadata={
                            "failed_attempts": len(recent_fail_count),
                            "cooldown_minutes": LOCKOUT_COOLDOWN_MINUTES,
                        },
                    )
                    session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid email or password",
        )
    # Time-bound access (tw-6to0): expired users are rejected with the
    # same generic 401. The audit event metadata.reason distinguishes.
    # SQLite returns naive datetimes; coerce to UTC for the comparison.
    if user.expires_at is not None:
        exp = user.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=UTC)
        if exp <= datetime.now(tz=UTC):
            _emit_auth_event(
                session,
                workspace_id=user.workspace_id,
                actor_id=user.id,
                event_type="auth.login.failed",
                metadata={**audit_meta, "reason": "expired"},
            )
            session.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid email or password",
            )
    # Disabled or soft-deleted accounts cannot log in. Return the same
    # 401 message either way — don't leak whether the email exists,
    # only that this user can't authenticate.
    if not user.enabled or user.deleted_at is not None:
        _emit_auth_event(
            session,
            workspace_id=user.workspace_id,
            actor_id=user.id,
            event_type="auth.login.failed",
            metadata={**audit_meta, "reason": "disabled_or_deleted"},
        )
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid email or password"
        )
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
    # tw-huzu: suspicious-login signals (new IP, new UA family, first login).
    ua = request.headers.get("user-agent", "")
    ua_family = _ua_family(ua)
    audit_meta["user_agent"] = ua
    audit_meta["ua_family"] = ua_family
    susp_reasons = _detect_suspicious(
        session,
        user_id=user.id,
        client_ip=client_ip,
        ua_family=ua_family,
    )
    audit_meta["suspicious"] = bool(susp_reasons)
    audit_meta["suspicious_reasons"] = susp_reasons
    _emit_auth_event(
        session,
        workspace_id=user.workspace_id,
        actor_id=user.id,
        event_type="auth.login.success",
        metadata=audit_meta,
    )
    if susp_reasons:
        _emit_auth_event(
            session,
            workspace_id=user.workspace_id,
            actor_id=user.id,
            event_type="auth.login.suspicious",
            metadata={
                "client_ip": client_ip,
                "ua_family": ua_family,
                "reasons": susp_reasons,
            },
        )
    session.commit()
    return UserOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        must_change_password=user.must_change_password,
        mfa_enabled=user.totp_enabled,
        tak_callsign=user.tak_callsign,
    )


@router.post("/logout")
def logout(
    response: Response,
    request: Request,
    settings: Settings = Depends(get_settings),
    session: Session = Depends(db_session),
) -> dict[str, str]:
    # Best-effort: if the caller had a valid session, record the logout
    # against them. Don't *enforce* auth on /logout — clearing the cookie
    # is harmless even when expired, and logout should not fail.
    tw_session = request.cookies.get(settings.session_cookie_name)
    user: UserTable | None = None
    if tw_session:
        user_id = verify_session(tw_session, settings.session_secret)
        if user_id is not None:
            user = session.exec(select(UserTable).where(UserTable.id == user_id)).first()
    if user is not None:
        _emit_auth_event(
            session,
            workspace_id=user.workspace_id,
            actor_id=user.id,
            event_type="auth.logout",
            metadata={},
        )
        session.commit()
    response.delete_cookie(
        key=settings.session_cookie_name,
        httponly=True,
        samesite="lax",
    )
    return {"status": "ok"}


@router.post("/sessions/revoke-all")
def revoke_all_sessions(
    user: UserTable = Depends(interactive_user),
    session: Session = Depends(db_session),
) -> dict[str, str]:
    """Invalidate every existing cookie for the authenticated user. tw-ptn2.

    Bumps user.session_version. The caller's own cookie also stops
    validating after this call returns — they'll need to log in again.
    """
    user.session_version = (user.session_version or 0) + 1
    session.add(user)
    _emit_auth_event(
        session,
        workspace_id=user.workspace_id,
        actor_id=user.id,
        event_type="auth.sessions.revoked",
        metadata={"new_session_version": user.session_version},
    )
    session.commit()
    return {"status": "ok"}


@router.get("/me", response_model=UserOut)
def me(user: UserTable = Depends(current_user)) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        must_change_password=user.must_change_password,
        mfa_enabled=user.totp_enabled,
        tak_callsign=user.tak_callsign,
    )


@router.post("/change-password", response_model=UserOut)
def change_password(
    body: ChangePasswordRequest,
    request: Request,
    response: Response,
    session: Session = Depends(db_session),
    settings: Settings = Depends(get_settings),
) -> UserOut:
    """Change the authenticated user's password.

    Allowed even when must_change_password=True (this is the endpoint
    that clears the flag). Re-resolves the session manually rather than
    using current_user so the must-change gate (which is mounted as a
    middleware on non-/v1/auth routes) doesn't accidentally block this
    route's own auth check.

    Per tw-4exk.
    """
    tw_session = request.cookies.get(settings.session_cookie_name)
    if not tw_session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    user_id = verify_session(tw_session, settings.session_secret)
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    user = session.exec(select(UserTable).where(UserTable.id == user_id)).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="not authenticated")
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="current password incorrect"
        )
    if body.new_password == body.current_password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="new password must differ from current password",
        )
    # tw-fn7a: enforce password policy on new password.
    from target_workspace.api.password_policy import validate_password  # noqa: PLC0415

    validate_password(body.new_password, settings)
    user.password_hash = hash_password(
        body.new_password,
        env=settings.env,
        bcrypt_rounds=settings.bcrypt_rounds,
    )
    user.must_change_password = False
    # tw-ptn2: auto-revoke all other sessions on password change.
    user.session_version = (user.session_version or 0) + 1
    session.add(user)
    _emit_auth_event(
        session,
        workspace_id=user.workspace_id,
        actor_id=user.id,
        event_type="auth.password.changed",
        metadata={},
    )
    session.commit()
    session.refresh(user)
    # tw-ptn2: session_version was bumped above; the caller's existing
    # cookie is now invalid. Re-issue a fresh cookie so the caller
    # doesn't have to log in again right after changing their password.
    new_token = sign_session(
        user.id,
        settings.session_secret,
        session_version=user.session_version,
    )
    response.set_cookie(
        key=settings.session_cookie_name,
        value=new_token,
        max_age=settings.session_max_age_seconds,
        httponly=True,
        samesite="lax",
        secure=secure_cookies_for_env(settings.env),
    )
    return UserOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        must_change_password=user.must_change_password,
        mfa_enabled=user.totp_enabled,
        tak_callsign=user.tak_callsign,
    )
