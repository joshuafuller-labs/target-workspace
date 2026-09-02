"""/v1/auth/passkeys - WebAuthn/passkey ceremonies."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session, select
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialCreationOptions,
    PublicKeyCredentialDescriptor,
    PublicKeyCredentialRequestOptions,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from target_workspace.api.auth import sign_session
from target_workspace.api.auth_audit import (
    default_workspace_id,
    detect_suspicious,
    emit_auth_event,
    ua_family,
)
from target_workspace.api.config import Settings, get_settings, secure_cookies_for_env
from target_workspace.api.dependencies import db_session, interactive_user
from target_workspace.api.schemas import UserOut
from target_workspace.db.tables import (
    PasskeyChallengeTable,
    PasskeyCredentialTable,
    UserTable,
)

router = APIRouter(prefix="/v1/auth/passkeys", tags=["passkeys"])

CHALLENGE_TTL = timedelta(minutes=5)


class PasskeyRegisterOptionsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)


class PasskeyVerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    challenge: str = Field(min_length=1)
    credential: dict[str, Any]
    name: str | None = Field(default=None, max_length=120)


class PasskeyOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    name: str
    created_at: datetime
    last_used_at: datetime | None = None
    aaguid: str | None = None


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _canonical_credential_id(value: object) -> str:
    if isinstance(value, str):
        try:
            return _b64url(_b64url_decode(value))
        except Exception:
            return value
    if isinstance(value, list) and all(isinstance(item, int) for item in value):
        return _b64url(bytes(value))
    return ""


def _credential_id_from_body(credential: dict[str, Any]) -> str:
    for key in ("id", "rawId"):
        credential_id = _canonical_credential_id(credential.get(key))
        if credential_id:
            return credential_id
    return ""


def _json_options(
    options: PublicKeyCredentialCreationOptions | PublicKeyCredentialRequestOptions,
) -> dict[str, Any]:
    public_key = json.loads(options_to_json(options))
    if public_key.get("allowCredentials") == []:
        del public_key["allowCredentials"]
    return {"publicKey": public_key}


def _first_forwarded_value(value: str | None) -> str:
    return (value or "").split(",", maxsplit=1)[0].strip()


def _host_without_port(host: str) -> str:
    if host.startswith("["):
        return host.removeprefix("[").split("]", maxsplit=1)[0]
    return host.split(":", maxsplit=1)[0]


def _request_host(request: Request) -> str:
    forwarded_host = _first_forwarded_value(request.headers.get("x-forwarded-host"))
    if forwarded_host:
        return forwarded_host
    return request.url.netloc or request.url.hostname or "localhost"


def _request_scheme(request: Request) -> str:
    forwarded_proto = _first_forwarded_value(request.headers.get("x-forwarded-proto"))
    return forwarded_proto or request.url.scheme


def _rp_id(request: Request, settings: Settings) -> str:
    if settings.webauthn_rp_id:
        return settings.webauthn_rp_id
    return _host_without_port(_request_host(request)) or "localhost"


def _origin(request: Request, settings: Settings) -> str:
    if settings.webauthn_origin:
        return settings.webauthn_origin
    return f"{_request_scheme(request)}://{_request_host(request)}"


def _client_ip(request: Request) -> str:
    forwarded_for = _first_forwarded_value(request.headers.get("x-forwarded-for"))
    if forwarded_for:
        return forwarded_for
    if request.client:
        return request.client.host
    return "unknown"


def _passkey_audit_metadata(
    request: Request,
    *,
    user: UserTable | None,
    passkey: PasskeyCredentialTable | None,
    reason: str | None = None,
) -> dict[str, Any]:
    client_ip = _client_ip(request)
    user_agent = request.headers.get("user-agent", "")
    metadata: dict[str, Any] = {
        "method": "passkey",
        "user_agent": user_agent,
        "ua_family": ua_family(user_agent),
    }
    if user is not None:
        metadata["email"] = user.email
    if client_ip != "unknown":
        metadata["client_ip"] = client_ip
    if passkey is not None:
        metadata["passkey_id"] = str(passkey.id)
        metadata["passkey_name"] = passkey.name
    if reason is not None:
        metadata["reason"] = reason
    return metadata


def _passkey_registration_audit_metadata(
    request: Request,
    *,
    user: UserTable,
    passkey: PasskeyCredentialTable | None = None,
    passkey_name: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    metadata = _passkey_audit_metadata(
        request,
        user=user,
        passkey=passkey,
        reason=reason,
    )
    if passkey is None and passkey_name:
        metadata["passkey_name"] = passkey_name
    return metadata


def _audit_workspace_id(session: Session, user: UserTable | None) -> UUID | None:
    return user.workspace_id if user is not None else default_workspace_id(session)


def _store_challenge(
    session: Session,
    *,
    challenge: bytes,
    ceremony: str,
    user_id: UUID | None,
    name: str | None = None,
) -> str:
    value = _b64url(challenge)
    session.add(
        PasskeyChallengeTable(
            challenge=value,
            ceremony=ceremony,
            user_id=user_id,
            name=name,
            created_at=datetime.now(tz=UTC),
            expires_at=datetime.now(tz=UTC) + CHALLENGE_TTL,
        ),
    )
    session.commit()
    return value


def _consume_challenge(
    session: Session,
    *,
    challenge: str,
    ceremony: str,
) -> PasskeyChallengeTable:
    row = session.get(PasskeyChallengeTable, challenge)
    now = datetime.now(tz=UTC)
    if row is None or row.ceremony != ceremony:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="challenge not pending")
    expires_at = row.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= now:
        session.delete(row)
        session.commit()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="challenge expired")
    session.delete(row)
    session.flush()
    return row


def _user_out(user: UserTable) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        must_change_password=user.must_change_password,
        mfa_enabled=user.totp_enabled,
        tak_callsign=user.tak_callsign,
    )


@router.get("", response_model=list[PasskeyOut])
def list_passkeys(
    user: UserTable = Depends(interactive_user),
    session: Session = Depends(db_session),
) -> list[PasskeyCredentialTable]:
    return list(
        session.exec(
            select(PasskeyCredentialTable).where(PasskeyCredentialTable.user_id == user.id),
        ).all(),
    )


@router.post("/register/options")
def register_options(
    body: PasskeyRegisterOptionsRequest,
    request: Request,
    user: UserTable = Depends(interactive_user),
    session: Session = Depends(db_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    existing = session.exec(
        select(PasskeyCredentialTable).where(PasskeyCredentialTable.user_id == user.id),
    ).all()
    options = generate_registration_options(
        rp_id=_rp_id(request, settings),
        rp_name="Target Workspace",
        user_id=user.id.bytes,
        user_name=user.email,
        user_display_name=user.display_name,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            require_resident_key=True,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=_b64url_decode(item.credential_id))
            for item in existing
        ],
    )
    _store_challenge(
        session,
        challenge=options.challenge,
        ceremony="registration",
        user_id=user.id,
        name=body.name,
    )
    return _json_options(options)


@router.post("/register/verify", response_model=PasskeyOut, status_code=status.HTTP_201_CREATED)
def register_verify(
    body: PasskeyVerifyRequest,
    request: Request,
    session: Session = Depends(db_session),
    user: UserTable = Depends(interactive_user),
    settings: Settings = Depends(get_settings),
) -> PasskeyCredentialTable:
    challenge = _consume_challenge(session, challenge=body.challenge, ceremony="registration")
    if challenge.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="challenge owner mismatch")
    try:
        verified = verify_registration_response(
            credential=body.credential,
            expected_challenge=_b64url_decode(body.challenge),
            expected_rp_id=_rp_id(request, settings),
            expected_origin=_origin(request, settings),
            require_user_verification=False,
        )
    except Exception as exc:
        emit_auth_event(
            session,
            workspace_id=user.workspace_id,
            actor_id=user.id,
            event_type="auth.passkey.registration.failed",
            metadata=_passkey_registration_audit_metadata(
                request,
                user=user,
                passkey_name=body.name or challenge.name or "Passkey",
                reason="invalid_passkey",
            ),
        )
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid passkey",
        ) from exc

    credential_id = _b64url(verified.credential_id)
    existing = session.exec(
        select(PasskeyCredentialTable).where(
            PasskeyCredentialTable.credential_id == credential_id,
        ),
    ).first()
    if existing is not None:
        session.commit()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="passkey already exists")

    row = PasskeyCredentialTable(
        user_id=user.id,
        name=body.name or challenge.name or "Passkey",
        credential_id=credential_id,
        public_key=_b64url(verified.credential_public_key),
        sign_count=verified.sign_count,
        aaguid=verified.aaguid,
        created_at=datetime.now(tz=UTC),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    emit_auth_event(
        session,
        workspace_id=user.workspace_id,
        actor_id=user.id,
        event_type="auth.passkey.registration.success",
        metadata=_passkey_registration_audit_metadata(
            request,
            user=user,
            passkey=row,
        ),
    )
    session.commit()
    return row


@router.post("/authenticate/options")
def authentication_options(
    request: Request,
    session: Session = Depends(db_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    options = generate_authentication_options(
        rp_id=_rp_id(request, settings),
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    _store_challenge(
        session,
        challenge=options.challenge,
        ceremony="authentication",
        user_id=None,
    )
    return _json_options(options)


@router.post("/authenticate/verify", response_model=UserOut)
def authentication_verify(
    body: PasskeyVerifyRequest,
    request: Request,
    response: Response,
    session: Session = Depends(db_session),
    settings: Settings = Depends(get_settings),
) -> UserOut:
    _consume_challenge(session, challenge=body.challenge, ceremony="authentication")
    credential_id = _credential_id_from_body(body.credential)
    row = session.exec(
        select(PasskeyCredentialTable).where(PasskeyCredentialTable.credential_id == credential_id),
    ).first()
    if row is None:
        workspace_id = default_workspace_id(session)
        if workspace_id is not None:
            emit_auth_event(
                session,
                workspace_id=workspace_id,
                actor_id=None,
                event_type="auth.login.failed",
                metadata=_passkey_audit_metadata(
                    request,
                    user=None,
                    passkey=None,
                    reason="unknown_passkey",
                ),
            )
        session.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="unknown passkey")
    user = session.get(UserTable, row.user_id)
    try:
        verified = verify_authentication_response(
            credential=body.credential,
            expected_challenge=_b64url_decode(body.challenge),
            expected_rp_id=_rp_id(request, settings),
            expected_origin=_origin(request, settings),
            credential_public_key=_b64url_decode(row.public_key),
            credential_current_sign_count=row.sign_count,
            require_user_verification=False,
        )
    except Exception as exc:
        workspace_id = _audit_workspace_id(session, user)
        if workspace_id is not None:
            emit_auth_event(
                session,
                workspace_id=workspace_id,
                actor_id=row.user_id,
                event_type="auth.login.failed",
                metadata=_passkey_audit_metadata(
                    request,
                    user=user,
                    passkey=row,
                    reason="invalid_passkey",
                ),
            )
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid passkey",
        ) from exc

    if _b64url(verified.credential_id) != row.credential_id:
        workspace_id = _audit_workspace_id(session, user)
        if workspace_id is not None:
            emit_auth_event(
                session,
                workspace_id=workspace_id,
                actor_id=row.user_id,
                event_type="auth.login.failed",
                metadata=_passkey_audit_metadata(
                    request,
                    user=user,
                    passkey=row,
                    reason="credential_mismatch",
                ),
            )
        session.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="credential mismatch")
    if user is None or not user.enabled or user.deleted_at is not None:
        workspace_id = _audit_workspace_id(session, user)
        if workspace_id is not None:
            emit_auth_event(
                session,
                workspace_id=workspace_id,
                actor_id=row.user_id,
                event_type="auth.login.failed",
                metadata=_passkey_audit_metadata(
                    request,
                    user=user,
                    passkey=row,
                    reason="user_unavailable",
                ),
            )
        session.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user unavailable")
    row.sign_count = verified.new_sign_count
    row.last_used_at = datetime.now(tz=UTC)
    session.add(row)
    metadata = _passkey_audit_metadata(request, user=user, passkey=row)
    suspicious_reasons = detect_suspicious(
        session,
        user_id=user.id,
        client_ip=str(metadata.get("client_ip", "")),
        ua_family_value=str(metadata.get("ua_family", "")),
    )
    metadata["suspicious"] = bool(suspicious_reasons)
    metadata["suspicious_reasons"] = suspicious_reasons
    emit_auth_event(
        session,
        workspace_id=user.workspace_id,
        actor_id=user.id,
        event_type="auth.login.success",
        metadata=metadata,
    )
    if suspicious_reasons:
        emit_auth_event(
            session,
            workspace_id=user.workspace_id,
            actor_id=user.id,
            event_type="auth.login.suspicious",
            metadata={
                "method": "passkey",
                "client_ip": metadata.get("client_ip"),
                "ua_family": metadata.get("ua_family"),
                "reasons": suspicious_reasons,
            },
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
    session.commit()
    return _user_out(user)


@router.delete("/{passkey_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_passkey(
    passkey_id: UUID,
    user: UserTable = Depends(interactive_user),
    session: Session = Depends(db_session),
) -> None:
    row = session.get(PasskeyCredentialTable, passkey_id)
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="passkey not found")
    session.delete(row)
    session.commit()
