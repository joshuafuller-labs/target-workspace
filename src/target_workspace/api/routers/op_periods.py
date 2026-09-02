"""/v1/boards/{board_id}/op-periods — ICS operational period CRUD (tw-eebq).

One active period per board. Opening a new period auto-closes the
previous active one.
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
from target_workspace.db.tables import BoardTable, OpPeriodTable, UserTable

router = APIRouter(prefix="/v1/boards", tags=["op_periods"])


class OpPeriodCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    iap: dict[str, Any] | None = None


class OpPeriodOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    board_id: UUID
    number: int
    started_at: datetime
    ends_at: datetime | None
    started_by_user_id: UUID
    closed_by_user_id: UUID | None
    status: str
    iap: dict[str, Any] | None


def _to_out(row: OpPeriodTable) -> dict[str, Any]:
    return {
        "id": row.id,
        "board_id": row.board_id,
        "number": row.number,
        "started_at": row.started_at,
        "ends_at": row.ends_at,
        "started_by_user_id": row.started_by_user_id,
        "closed_by_user_id": row.closed_by_user_id,
        "status": row.status,
        "iap": row.iap,
    }


def _verify_board(session: Session, board_id: UUID, workspace_id: UUID) -> None:
    board = session.get(BoardTable, board_id)
    if board is None or board.workspace_id != workspace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="board not found",
        )


@router.post(
    "/{board_id}/op-periods",
    response_model=OpPeriodOut,
    status_code=status.HTTP_201_CREATED,
)
def open_op_period(
    board_id: UUID,
    body: OpPeriodCreate,
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("op_periods:write")),
) -> dict[str, Any]:
    require_role(user.role, "commander", action="open op period")
    _verify_board(session, board_id, user.workspace_id)

    # Auto-close any active period for this board.
    active = session.exec(
        select(OpPeriodTable)
        .where(OpPeriodTable.board_id == board_id)
        .where(OpPeriodTable.status == "active"),
    ).all()
    now = datetime.now(tz=UTC)
    for prev in active:
        prev.ends_at = now
        prev.status = "closed"
        prev.closed_by_user_id = user.id
        session.add(prev)
    session.flush()

    # Compute the next period number.
    existing = session.exec(
        select(OpPeriodTable).where(OpPeriodTable.board_id == board_id),
    ).all()
    next_number = (max((p.number for p in existing), default=0)) + 1

    row = OpPeriodTable(
        id=uuid4(),
        board_id=board_id,
        number=next_number,
        started_at=now,
        ends_at=None,
        started_by_user_id=user.id,
        closed_by_user_id=None,
        status="active",
        iap=body.iap,
    )
    session.add(row)
    session.flush()
    return _to_out(row)


@router.get("/{board_id}/op-periods", response_model=list[OpPeriodOut])
def list_op_periods(
    board_id: UUID,
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("op_periods:read")),
) -> list[dict[str, Any]]:
    _verify_board(session, board_id, user.workspace_id)
    rows = session.exec(
        select(OpPeriodTable)
        .where(OpPeriodTable.board_id == board_id)
        .order_by(OpPeriodTable.number),  # type: ignore[arg-type]
    ).all()
    return [_to_out(r) for r in rows]
