"""/v1/resources — ICS-211 resource roster (tw-qkp)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session, select

from target_workspace.api.dependencies import db_session, require_token_scope
from target_workspace.db.tables import ResourceTable, UserTable

router = APIRouter(prefix="/v1/resources", tags=["resources"])


class ResourceCheckIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    callsign: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    certifications: list[str] = Field(default_factory=list)
    location: str | None = Field(default=None, max_length=200)


class ResourceOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    callsign: str
    name: str
    certifications: list[str]
    location: str | None
    status: str
    checked_in_at: datetime
    checked_out_at: datetime | None


def _to_out(r: ResourceTable) -> dict[str, Any]:
    return {
        "id": r.id,
        "callsign": r.callsign,
        "name": r.name,
        "certifications": list(r.certifications or []),
        "location": r.location,
        "status": r.status,
        "checked_in_at": r.checked_in_at,
        "checked_out_at": r.checked_out_at,
    }


@router.post("", response_model=ResourceOut, status_code=status.HTTP_201_CREATED)
def check_in(
    body: ResourceCheckIn,
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("resources:write")),
) -> dict[str, Any]:
    row = ResourceTable(
        id=uuid4(),
        workspace_id=user.workspace_id,
        callsign=body.callsign,
        name=body.name,
        certifications=list(body.certifications),
        location=body.location,
        status="checked-in",
        checked_in_at=datetime.now(tz=UTC),
        checked_out_at=None,
    )
    session.add(row)
    session.flush()
    return _to_out(row)


@router.get("", response_model=list[ResourceOut])
def list_roster(
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("resources:read")),
) -> list[dict[str, Any]]:
    """Current roster — checked-in only. Use /history for departed."""
    rows = session.exec(
        select(ResourceTable)
        .where(ResourceTable.workspace_id == user.workspace_id)
        .where(ResourceTable.status == "checked-in"),
    ).all()
    return [_to_out(r) for r in rows]


@router.post("/{resource_id}/check-out", response_model=ResourceOut)
def check_out(
    resource_id: UUID,
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("resources:write")),
) -> dict[str, Any]:
    row = session.get(ResourceTable, resource_id)
    if row is None or row.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="resource not found")
    row.status = "checked-out"
    row.checked_out_at = datetime.now(tz=UTC)
    session.add(row)
    session.flush()
    return _to_out(row)


@router.get("/history", response_model=list[ResourceOut])
def list_history(
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("resources:read")),
) -> list[dict[str, Any]]:
    rows = session.exec(
        select(ResourceTable)
        .where(ResourceTable.workspace_id == user.workspace_id)
        .order_by(ResourceTable.checked_in_at),  # type: ignore[arg-type]
    ).all()
    return [_to_out(r) for r in rows]
