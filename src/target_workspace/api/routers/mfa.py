"""/v1/auth/mfa/totp — TOTP enrollment + activation + disable (tw-mg1a).

Login-challenge integration (require TOTP after password) is a v1.1
follow-up because it changes the cookie payload + dependency contract.
Recovery codes also defer to v1.1.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session

from target_workspace.api.auth import verify_password
from target_workspace.api.dependencies import db_session, interactive_user
from target_workspace.api.totp import (
    generate_secret,
    provisioning_uri,
    verify_code,
)
from target_workspace.db.tables import UserTable

router = APIRouter(prefix="/v1/auth/mfa/totp", tags=["mfa"])


class TotpEnrollResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    secret: str
    provisioning_uri: str


class TotpCode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str = Field(min_length=4, max_length=10)


class TotpDisable(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str = Field(min_length=1)
    code: str = Field(min_length=4, max_length=10)


@router.post("/enroll", response_model=TotpEnrollResponse)
def enroll(
    session: Session = Depends(db_session),
    user: UserTable = Depends(interactive_user),
) -> dict[str, Any]:
    """Generate a fresh TOTP secret for this user and return the
    provisioning URI for QR-code rendering. The secret is stored as
    pending until verify-enroll is called with a valid code."""
    secret = generate_secret()
    user.totp_secret = secret
    user.totp_enabled = False  # not until verified
    user.totp_activated_at = None
    session.add(user)
    session.flush()
    return {
        "secret": secret,
        "provisioning_uri": provisioning_uri(
            secret_b32=secret,
            account_name=user.email,
        ),
    }


@router.post("/verify-enroll")
def verify_enroll(
    body: TotpCode,
    session: Session = Depends(db_session),
    user: UserTable = Depends(interactive_user),
) -> dict[str, Any]:
    """Verify the first TOTP code and activate MFA."""
    if not user.totp_secret:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="no pending TOTP enrollment; call /enroll first",
        )
    if not verify_code(user.totp_secret, body.code):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid TOTP code",
        )
    user.totp_enabled = True
    user.totp_activated_at = datetime.now(tz=UTC)
    session.add(user)
    session.flush()
    return {"mfa_enabled": True}


@router.post("/disable")
def disable(
    body: TotpDisable,
    session: Session = Depends(db_session),
    user: UserTable = Depends(interactive_user),
) -> dict[str, Any]:
    """Disable TOTP. Requires the current password AND a valid TOTP code."""
    if not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="password incorrect",
        )
    if not user.totp_secret or not verify_code(user.totp_secret, body.code):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid TOTP code",
        )
    user.totp_secret = None
    user.totp_enabled = False
    user.totp_activated_at = None
    session.add(user)
    session.flush()
    return {"mfa_enabled": False}
