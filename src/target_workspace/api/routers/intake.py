"""/v1/intake — unauthenticated public-submission endpoints (tw-858).

Welfare-check intake from outside-the-zone relatives + concerned
citizens. Each submission lands on the configured intake board's
unmoderated column. Operators triage from there.

Rate-limited per source IP. No auth — that's the point; citizens
have no accounts.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session, col, select

from target_workspace.api.dependencies import db_session
from target_workspace.api.ratelimit import check_and_record
from target_workspace.db.tables import (
    BoardTable,
    ColumnTable,
    TargetTable,
    WorkspaceTable,
)

router = APIRouter(prefix="/v1/intake", tags=["intake"])

RATE_LIMIT_BUCKET = "intake.welfare.ip"


class WelfareCheckIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    intake_board: str = Field(min_length=1, max_length=120)
    address: str = Field(min_length=1, max_length=500)
    description: str = Field(min_length=1, max_length=2000)
    reporter_name: str = Field(min_length=1, max_length=200)
    reporter_contact: str = Field(min_length=1, max_length=200)
    subject_name: str = Field(min_length=1, max_length=200)
    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


@router.post("/welfare-check", status_code=status.HTTP_201_CREATED)
def submit_welfare_check(
    body: WelfareCheckIn,
    request: Request,
    session: Session = Depends(db_session),
) -> dict[str, Any]:
    """Citizen-facing welfare-check submission.

    Lands as a Target on the named board's first column. Carries
    custom_fields.intake_unmoderated=true so the SPA can render an
    'Unreviewed' badge until an operator triages it.
    """
    client_ip = _client_ip(request)
    allowed, retry = check_and_record(bucket=RATE_LIMIT_BUCKET, key=client_ip)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="too many submissions; try again later",
            headers={"Retry-After": str(retry)},
        )

    # Pick the workspace + board. MVP: first workspace, named board.
    ws = session.exec(
        select(WorkspaceTable).order_by(col(WorkspaceTable.created_at)),
    ).first()
    if ws is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="workspace not configured",
        )
    board = session.exec(
        select(BoardTable)
        .where(BoardTable.workspace_id == ws.id)
        .where(BoardTable.name == body.intake_board),
    ).first()
    if board is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"intake board '{body.intake_board}' not found",
        )
    cols = session.exec(
        select(ColumnTable)
        .where(ColumnTable.board_id == board.id)
        .order_by(col(ColumnTable.order)),
    ).all()
    if not cols:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="intake board has no columns",
        )
    first_col = cols[0]

    target_id = uuid4()
    now = datetime.now(tz=UTC)
    target = TargetTable(
        id=target_id,
        workspace_id=ws.id,
        board_id=board.id,
        column_id=first_col.id,
        name=f"WELFARE · {body.subject_name}",
        cot_type="a-u-G-U-C",
        lat=body.lat,
        lon=body.lon,
        time=now,
        custom_fields={
            "intake_unmoderated": True,
            "intake_kind": "welfare-check",
            "address": body.address,
            "description": body.description,
            "reporter_name": body.reporter_name,
            "reporter_contact": body.reporter_contact,
            "subject_name": body.subject_name,
            "client_ip": client_ip,
        },
        version=1,
        position=0,
        created_at=now,
        updated_at=now,
    )
    session.add(target)
    session.flush()

    # Append an unattributed audit event. actor_id is null because the
    # submitter is anonymous; reviewers will see the metadata.
    from target_workspace.api.signing import sign_audit_event  # noqa: PLC0415
    from target_workspace.db.tables import AuditEventTable  # noqa: PLC0415

    audit = AuditEventTable(
        workspace_id=ws.id,
        target_id=target_id,
        actor_id=None,
        event_type="intake.welfare_check.received",
        occurred_at=now,
        metadata_json={
            "client_ip": client_ip,
            "reporter_name": body.reporter_name,
            "subject_name": body.subject_name,
        },
    )
    session.add(audit)
    session.flush()
    peer_id, sig, prev_hash = sign_audit_event(
        session,
        event_id=audit.id,
        workspace_id=audit.workspace_id,
        actor_id=None,
        event_type=audit.event_type,
        target_id=audit.target_id,
        occurred_at=audit.occurred_at,
        metadata=audit.metadata_json,
    )
    audit.peer_id = peer_id
    audit.prev_hash = prev_hash
    audit.signature = sig
    session.add(audit)
    session.flush()

    return {"status": "queued", "id": str(target_id)}
