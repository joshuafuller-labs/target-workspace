"""/v1/workspaces/me — workspace-scoped settings CRUD (tw-smc).

GET is any authenticated user. PATCH requires admin.

Mutable knobs:
  - brand_name                    (str | null — falls back to BRAND_NAME env)
  - default_theme                 (neutral | tactical | federal | sar | ics)
  - freshness_active_seconds      (int > 0)
  - freshness_coasting_seconds    (int > active)
  - freshness_stale_seconds       (int > coasting)
  - correlation_radius_m          (float >= 0)
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session

from target_workspace.api.dependencies import db_session, require_token_scope
from target_workspace.api.rbac import require_role
from target_workspace.db.tables import UserTable, WorkspaceTable

router = APIRouter(prefix="/v1/workspaces/me", tags=["workspaces"])

_ALLOWED_THEMES = {"neutral", "tactical", "federal", "sar", "ics"}


class WorkspacePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    brand_name: str | None = Field(default=None, max_length=200)
    default_theme: str | None = Field(default=None, max_length=32)
    freshness_active_seconds: int | None = Field(default=None, gt=0, le=86400)
    freshness_coasting_seconds: int | None = Field(default=None, gt=0, le=86400)
    freshness_stale_seconds: int | None = Field(default=None, gt=0, le=86400)
    correlation_radius_m: float | None = Field(default=None, ge=0.0, le=100_000.0)


class WorkspaceOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    brand_name: str | None
    default_theme: str
    freshness_active_seconds: int
    freshness_coasting_seconds: int
    freshness_stale_seconds: int
    correlation_radius_m: float


def _to_out(row: WorkspaceTable) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "name": row.name,
        "brand_name": row.brand_name,
        "default_theme": row.default_theme,
        "freshness_active_seconds": row.freshness_active_seconds,
        "freshness_coasting_seconds": row.freshness_coasting_seconds,
        "freshness_stale_seconds": row.freshness_stale_seconds,
        "correlation_radius_m": row.correlation_radius_m,
    }


def _load(session: Session, user: UserTable) -> WorkspaceTable:
    row = session.get(WorkspaceTable, user.workspace_id)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="workspace not found",
        )
    return row


@router.get("", response_model=WorkspaceOut)
def get_workspace(
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("workspace:read")),
) -> dict[str, Any]:
    return _to_out(_load(session, user))


@router.patch("", response_model=WorkspaceOut)
def patch_workspace(
    body: WorkspacePatch,
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("workspace:write")),
) -> dict[str, Any]:
    require_role(user.role, "admin", action="patch workspace settings")
    row = _load(session, user)
    fields = body.model_dump(exclude_unset=True)
    if "default_theme" in fields and fields["default_theme"] not in _ALLOWED_THEMES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"default_theme must be one of {sorted(_ALLOWED_THEMES)}",
        )
    for k, v in fields.items():
        setattr(row, k, v)
    # Enforce freshness ordering — coasting > active, stale > coasting.
    if row.freshness_coasting_seconds <= row.freshness_active_seconds:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="freshness_coasting_seconds must exceed freshness_active_seconds",
        )
    if row.freshness_stale_seconds <= row.freshness_coasting_seconds:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="freshness_stale_seconds must exceed freshness_coasting_seconds",
        )
    session.add(row)
    session.flush()
    return _to_out(row)
