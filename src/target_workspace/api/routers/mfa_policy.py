"""/v1/workspace/mfa-policy — admin-managed MFA enforcement policy (tw-r1ru).

Workspace-level: which roles MUST have totp_enabled before they can
be granted. Default empty. The enforcement hook lives on the user
PATCH path; this router is just the policy CRUD.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session

from target_workspace.api.dependencies import db_session, require_token_scope
from target_workspace.api.rbac import require_role
from target_workspace.db.tables import UserTable, WorkspaceTable

router = APIRouter(prefix="/v1/workspace/mfa-policy", tags=["mfa-policy"])

_TIERS = {"admin", "commander", "operator", "analyst", "observer", "viewer"}


class MfaPolicyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    required_for_roles: list[str] = Field(default_factory=list)


class MfaPolicyOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    required_for_roles: list[str]


def _get_workspace(session: Session, user: UserTable) -> WorkspaceTable:
    ws = session.get(WorkspaceTable, user.workspace_id)
    if ws is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="workspace not found",
        )
    return ws


@router.get("", response_model=MfaPolicyOut)
def get_policy(
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("workspace:read")),
) -> dict[str, Any]:
    ws = _get_workspace(session, user)
    return {"required_for_roles": list(ws.mfa_required_roles or [])}


@router.put("", response_model=MfaPolicyOut)
def set_policy(
    body: MfaPolicyIn,
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("workspace:write")),
) -> dict[str, Any]:
    require_role(user.role, "admin", action="set workspace MFA policy")
    unknown = [r for r in body.required_for_roles if r not in _TIERS]
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"unknown role(s): {unknown}",
        )
    ws = _get_workspace(session, user)
    ws.mfa_required_roles = list(body.required_for_roles)
    session.add(ws)
    session.flush()
    return {"required_for_roles": list(ws.mfa_required_roles)}
