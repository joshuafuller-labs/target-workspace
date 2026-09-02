"""/v1/boards/{board_id}/workflow-triggers — geofence → column-move rules.

tw-5m91. Per-board rule storage; the engine that evaluates these on
PLI transitions lives in target_workspace.api.workflow_triggers.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session, select

from target_workspace.api.dependencies import db_session, require_token_scope
from target_workspace.api.rbac import require_role
from target_workspace.db.tables import (
    BoardTable,
    UserTable,
    WorkflowTriggerTable,
)

router = APIRouter(tags=["workflow-triggers"])

_ALLOWED_TRIGGERS = {"presence.arrived", "presence.departed"}


class WorkflowTriggerCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trigger: str
    condition: str = Field(default="any", max_length=128)
    action_move_to_column_id: UUID
    justification_template: str = Field(default="", max_length=500)


class WorkflowTriggerPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    trigger: str | None = None
    condition: str | None = Field(default=None, max_length=128)
    action_move_to_column_id: UUID | None = None
    justification_template: str | None = Field(default=None, max_length=500)


class WorkflowTriggerOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    board_id: UUID
    trigger: str
    condition: str
    action_move_to_column_id: UUID
    justification_template: str


def _to_out(row: WorkflowTriggerTable) -> dict[str, Any]:
    return {
        "id": row.id,
        "board_id": row.board_id,
        "trigger": row.trigger,
        "condition": row.condition,
        "action_move_to_column_id": row.action_move_to_column_id,
        "justification_template": row.justification_template,
    }


def _check_board_access(session: Session, board_id: UUID, user: UserTable) -> BoardTable:
    board = session.get(BoardTable, board_id)
    if board is None or board.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="board not found")
    return board


@router.post(
    "/v1/boards/{board_id}/workflow-triggers",
    response_model=WorkflowTriggerOut,
)
def create_trigger(
    board_id: UUID,
    body: WorkflowTriggerCreate,
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("workflow:write")),
) -> dict[str, Any]:
    require_role(user.role, "commander", action="create workflow trigger")
    _check_board_access(session, board_id, user)
    if body.trigger not in _ALLOWED_TRIGGERS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"trigger must be one of {sorted(_ALLOWED_TRIGGERS)}",
        )
    row = WorkflowTriggerTable(
        id=uuid4(),
        board_id=board_id,
        trigger=body.trigger,
        condition=body.condition,
        action_move_to_column_id=body.action_move_to_column_id,
        justification_template=body.justification_template,
    )
    session.add(row)
    session.flush()
    return _to_out(row)


@router.get(
    "/v1/boards/{board_id}/workflow-triggers",
    response_model=list[WorkflowTriggerOut],
)
def list_triggers(
    board_id: UUID,
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("workflow:read")),
) -> list[dict[str, Any]]:
    _check_board_access(session, board_id, user)
    rows = session.exec(
        select(WorkflowTriggerTable).where(WorkflowTriggerTable.board_id == board_id),
    ).all()
    return [_to_out(r) for r in rows]


@router.patch(
    "/v1/workflow-triggers/{trigger_id}",
    response_model=WorkflowTriggerOut,
)
def patch_trigger(
    trigger_id: UUID,
    body: WorkflowTriggerPatch,
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("workflow:write")),
) -> dict[str, Any]:
    require_role(user.role, "commander", action="patch workflow trigger")
    row = session.get(WorkflowTriggerTable, trigger_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="trigger not found")
    _check_board_access(session, row.board_id, user)
    if body.trigger is not None:
        if body.trigger not in _ALLOWED_TRIGGERS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"trigger must be one of {sorted(_ALLOWED_TRIGGERS)}",
            )
        row.trigger = body.trigger
    if body.condition is not None:
        row.condition = body.condition
    if body.action_move_to_column_id is not None:
        row.action_move_to_column_id = body.action_move_to_column_id
    if body.justification_template is not None:
        row.justification_template = body.justification_template
    session.add(row)
    session.flush()
    return _to_out(row)


@router.delete(
    "/v1/workflow-triggers/{trigger_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_trigger(
    trigger_id: UUID,
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("workflow:write")),
) -> None:
    require_role(user.role, "commander", action="delete workflow trigger")
    row = session.get(WorkflowTriggerTable, trigger_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="trigger not found")
    _check_board_access(session, row.board_id, user)
    session.delete(row)
    session.flush()
