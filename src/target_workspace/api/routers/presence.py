"""/v1/presence — PLI snapshot + per-callsign lookup (tw-6uz8)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session

from target_workspace.api.dependencies import db_session, require_token_scope
from target_workspace.api.presence import lookup, snapshot, upsert_pli
from target_workspace.api.rbac import require_role
from target_workspace.db.tables import UserTable
from target_workspace.workflow.presence import evaluate_presence_workflows

router = APIRouter(prefix="/v1/presence", tags=["presence"])


class PresenceIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    callsign: str = Field(min_length=1, max_length=64)
    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)
    hae: float | None = None
    ce: float | None = Field(default=None, ge=0.0)
    le: float | None = Field(default=None, ge=0.0)
    time: str
    course: float | None = None
    speed: float | None = None
    source: str | None = None


@router.get("")
def list_presence(
    user: UserTable = Depends(require_token_scope("presence:read")),
) -> list[dict[str, Any]]:
    _ = user
    return [e.to_json() for e in snapshot()]


@router.post("")
def post_presence(
    body: PresenceIn,
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("presence:write")),
) -> dict[str, Any]:
    require_role(user.role, "operator", action="upsert PLI presence")
    entry = upsert_pli(
        callsign=body.callsign,
        lat=body.lat,
        lon=body.lon,
        hae=body.hae,
        ce=body.ce,
        le=body.le,
        time_iso=body.time,
        course=body.course,
        speed=body.speed,
        source=body.source,
    )
    workflow_result = evaluate_presence_workflows(
        session,
        workspace_id=user.workspace_id,
        actor_id=user.id,
        callsign=body.callsign,
        lat=body.lat,
        lon=body.lon,
        ce=body.ce,
        source=body.source,
    )
    return {
        "presence": entry.to_json(),
        "transitions": workflow_result.transitions,
        "workflow_results": [outcome.to_json() for outcome in workflow_result.outcomes],
    }


@router.get("/{callsign}")
def get_presence(
    callsign: str,
    user: UserTable = Depends(require_token_scope("presence:read")),
) -> dict[str, Any]:
    _ = user
    entry = lookup(callsign)
    if entry is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="callsign offline")
    return entry.to_json()
