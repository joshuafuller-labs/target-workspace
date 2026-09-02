"""/v1/positions — ICS position-based authority (tw-l40z).

Standard ICS positions seeded on first access per workspace. Time-
windowed assignments with chain-of-custody on transfer.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlmodel import Session, select

from target_workspace.api.dependencies import db_session, require_token_scope
from target_workspace.api.rbac import require_role
from target_workspace.db.tables import (
    PositionAssignmentTable,
    PositionTable,
    UserTable,
)

router = APIRouter(prefix="/v1/positions", tags=["positions"])


STANDARD_ICS_POSITIONS: list[tuple[str, str, str]] = [
    ("Incident Commander", "IC", "Overall authority for the incident."),
    ("Deputy Incident Commander", "DIC", "Acts for the IC."),
    ("Operations Section Chief", "OSC", "Tactical operations + assignment list."),
    ("Planning Section Chief", "PSC", "Situation status + resource tracking."),
    ("Logistics Section Chief", "LSC", "Supplies + comms + medical + ground support."),
    ("Finance/Admin Section Chief", "FSC", "Cost + procurement + claims."),
    ("Safety Officer", "SAFETY", "Personnel safety + hazard assessment."),
    ("Public Information Officer", "PIO", "Media + public messaging."),
    ("Liaison Officer", "LIAISON", "Inter-agency representatives."),
]


def _seed_positions_if_missing(session: Session, workspace_id: UUID) -> None:
    """Ensure the standard ICS position roster exists for this workspace."""
    existing = session.exec(
        select(PositionTable).where(PositionTable.workspace_id == workspace_id),
    ).all()
    existing_codes = {p.ics_code for p in existing}
    now = datetime.now(tz=UTC)
    for name, code, desc in STANDARD_ICS_POSITIONS:
        if code in existing_codes:
            continue
        session.add(
            PositionTable(
                id=uuid4(),
                workspace_id=workspace_id,
                name=name,
                ics_code=code,
                description=desc,
                created_at=now,
            ),
        )
    session.flush()


class PositionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    name: str
    ics_code: str
    description: str | None


class AssignmentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    user_id: UUID
    op_period_id: UUID | None = None
    notes: str | None = None


class AssignmentOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    user_id: UUID
    op_period_id: UUID | None
    started_at: datetime
    ends_at: datetime | None
    transferred_from_assignment_id: UUID | None
    transferred_by_user_id: UUID | None
    notes: str | None


class PositionWithCurrent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    name: str
    ics_code: str
    assignment: AssignmentOut | None


@router.get("", response_model=list[PositionOut])
def list_positions(
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("positions:read")),
) -> list[dict[str, Any]]:
    _seed_positions_if_missing(session, user.workspace_id)
    rows = session.exec(
        select(PositionTable).where(PositionTable.workspace_id == user.workspace_id),
    ).all()
    return [
        {
            "id": r.id,
            "name": r.name,
            "ics_code": r.ics_code,
            "description": r.description,
        }
        for r in rows
    ]


@router.get("/current", response_model=list[PositionWithCurrent])
def current_holders(
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("positions:read")),
) -> list[dict[str, Any]]:
    _seed_positions_if_missing(session, user.workspace_id)
    positions = session.exec(
        select(PositionTable).where(PositionTable.workspace_id == user.workspace_id),
    ).all()
    out: list[dict[str, Any]] = []
    for p in positions:
        active = session.exec(
            select(PositionAssignmentTable)
            .where(PositionAssignmentTable.position_id == p.id)
            .where(PositionAssignmentTable.ends_at.is_(None)),  # type: ignore[union-attr]
        ).first()
        out.append(
            {
                "id": p.id,
                "name": p.name,
                "ics_code": p.ics_code,
                "assignment": (
                    {
                        "id": active.id,
                        "user_id": active.user_id,
                        "op_period_id": active.op_period_id,
                        "started_at": active.started_at,
                        "ends_at": active.ends_at,
                        "transferred_from_assignment_id": (active.transferred_from_assignment_id),
                        "transferred_by_user_id": active.transferred_by_user_id,
                        "notes": active.notes,
                    }
                    if active
                    else None
                ),
            },
        )
    return out


@router.post(
    "/{position_id}/assignments",
    response_model=AssignmentOut,
    status_code=status.HTTP_201_CREATED,
)
def assign_position(
    position_id: UUID,
    body: AssignmentBody,
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("positions:write")),
) -> dict[str, Any]:
    require_role(user.role, "commander", action="assign position")
    pos = session.get(PositionTable, position_id)
    if pos is None or pos.workspace_id != user.workspace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="position not found",
        )
    target = session.get(UserTable, body.user_id)
    if target is None or target.workspace_id != user.workspace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="user not found",
        )

    now = datetime.now(tz=UTC)
    # Close any active assignment on this position.
    prior = session.exec(
        select(PositionAssignmentTable)
        .where(PositionAssignmentTable.position_id == position_id)
        .where(PositionAssignmentTable.ends_at.is_(None)),  # type: ignore[union-attr]
    ).first()
    transferred_from = None
    if prior is not None:
        prior.ends_at = now
        prior.transferred_by_user_id = user.id
        session.add(prior)
        transferred_from = prior.id

    row = PositionAssignmentTable(
        id=uuid4(),
        position_id=position_id,
        user_id=body.user_id,
        op_period_id=body.op_period_id,
        started_at=now,
        ends_at=None,
        transferred_from_assignment_id=transferred_from,
        transferred_by_user_id=user.id if transferred_from else None,
        notes=body.notes,
    )
    session.add(row)
    session.flush()

    # tw-l40z: emit position.assigned audit event.
    from target_workspace.api.routers.password_reset import (  # noqa: PLC0415
        _emit_password_event as _emit,
    )

    _emit(
        session,
        workspace_id=user.workspace_id,
        actor_id=user.id,
        event_type="position.assigned",
        metadata={
            "position_id": str(position_id),
            "ics_code": pos.ics_code,
            "assigned_user_id": str(body.user_id),
            "transferred_from_assignment_id": (str(transferred_from) if transferred_from else None),
        },
    )
    session.commit()
    return {
        "id": row.id,
        "user_id": row.user_id,
        "op_period_id": row.op_period_id,
        "started_at": row.started_at,
        "ends_at": row.ends_at,
        "transferred_from_assignment_id": row.transferred_from_assignment_id,
        "transferred_by_user_id": row.transferred_by_user_id,
        "notes": row.notes,
    }


@router.get(
    "/{position_id}/history",
    response_model=list[AssignmentOut],
)
def list_history(
    position_id: UUID,
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("positions:read")),
) -> list[dict[str, Any]]:
    pos = session.get(PositionTable, position_id)
    if pos is None or pos.workspace_id != user.workspace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="position not found",
        )
    rows = session.exec(
        select(PositionAssignmentTable)
        .where(PositionAssignmentTable.position_id == position_id)
        .order_by(PositionAssignmentTable.started_at),  # type: ignore[arg-type]
    ).all()
    return [
        {
            "id": r.id,
            "user_id": r.user_id,
            "op_period_id": r.op_period_id,
            "started_at": r.started_at,
            "ends_at": r.ends_at,
            "transferred_from_assignment_id": r.transferred_from_assignment_id,
            "transferred_by_user_id": r.transferred_by_user_id,
            "notes": r.notes,
        }
        for r in rows
    ]
