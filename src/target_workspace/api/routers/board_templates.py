"""/v1/board-templates — 4-tile template picker + clone (tw-z9g).

Templates are hard-coded at MVP. Workspace-defined templates are a
follow-up.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session, select

from target_workspace.api.dependencies import db_session, require_token_scope
from target_workspace.api.rbac import require_role
from target_workspace.api.realtime import get_broker, make_event
from target_workspace.db import repositories as repo
from target_workspace.db.tables import (
    BoardTable,
    ColumnTable,
    UserTable,
)
from target_workspace.models.board import Board, Column

router = APIRouter(prefix="/v1/board-templates", tags=["board-templates"])


# Hard-coded template roster per the 2026-05-17 design.
TEMPLATES: dict[str, dict[str, Any]] = {
    "ics": {
        "id": "ics",
        "name": "ICS (Incident Command)",
        "description": "Generic ICS operations workflow.",
        "theme": "ics",
        "columns": [
            {"name": "Pending", "order": 0, "requires_approval": False},
            {"name": "Assigned", "order": 1, "requires_approval": False},
            {"name": "Active", "order": 2, "requires_approval": False},
            {"name": "Complete", "order": 3, "requires_approval": True},
        ],
    },
    "sar": {
        "id": "sar",
        "name": "SAR (Search & Rescue)",
        "description": "Missing-person + welfare-check workflow.",
        "theme": "sar",
        "columns": [
            {"name": "Reported", "order": 0, "requires_approval": False},
            {"name": "Search", "order": 1, "requires_approval": False},
            {"name": "Found", "order": 2, "requires_approval": True},
            {"name": "Reunified", "order": 3, "requires_approval": True},
        ],
    },
    "medical-triage": {
        "id": "medical-triage",
        "name": "Medical Triage",
        "description": "Mass-casualty triage + transport.",
        "theme": "ics",
        "columns": [
            {"name": "Intake", "order": 0, "requires_approval": False},
            {"name": "Triage", "order": 1, "requires_approval": False},
            {"name": "Treatment", "order": 2, "requires_approval": True},
            {"name": "Transport", "order": 3, "requires_approval": True},
            {"name": "Released", "order": 4, "requires_approval": False},
        ],
    },
    "f3ead": {
        "id": "f3ead",
        "name": "F3EAD (Targeting Cycle)",
        "description": "Find, Fix, Finish, Exploit, Analyze, Disseminate.",
        "theme": "tactical",
        "columns": [
            {"name": "Find", "order": 0, "requires_approval": False},
            {"name": "Fix", "order": 1, "requires_approval": False},
            {"name": "Finish", "order": 2, "requires_approval": True},
            {"name": "Exploit", "order": 3, "requires_approval": False},
            {"name": "Analyze", "order": 4, "requires_approval": False},
            {"name": "Disseminate", "order": 5, "requires_approval": True},
        ],
    },
}


class TemplateOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    name: str
    description: str
    theme: str


class InstantiateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)


class CloneBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)


@router.get("", response_model=list[TemplateOut])
def list_templates(
    user: UserTable = Depends(require_token_scope("templates:read")),
) -> list[dict[str, Any]]:
    return [
        {
            "id": t["id"],
            "name": t["name"],
            "description": t["description"],
            "theme": t["theme"],
        }
        for t in TEMPLATES.values()
    ]


@router.post(
    "/{template_id}/instantiate",
    response_model=Board,
    status_code=status.HTTP_201_CREATED,
)
def instantiate_template(
    template_id: str,
    body: InstantiateBody,
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("templates:write")),
) -> Board:
    require_role(user.role, "commander", action="instantiate board template")
    tpl = TEMPLATES.get(template_id)
    if tpl is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="template not found")
    board = Board(
        name=body.name,
        transitions="unrestricted",
        theme=tpl["theme"],
        columns=[
            Column(
                name=c["name"],
                order=c["order"],
                requires_approval=c.get("requires_approval", False),
            )
            for c in tpl["columns"]
        ],
    )
    repo.create_board(session, user.workspace_id, board)
    get_broker().publish(
        user.workspace_id,
        make_event(
            event_type="board.created",
            workspace_id=user.workspace_id,
            board_id=board.id,
            occurred_at=datetime.now(tz=UTC).isoformat(),
            data={"name": board.name, "theme": board.theme, "template": template_id},
        ),
    )
    return board


# Clone-from-board lives on the boards router conceptually, but we
# expose it here so it sits alongside the template picker UX.
clone_router = APIRouter(prefix="/v1/boards", tags=["board-templates"])


@clone_router.post(
    "/{board_id}/clone",
    response_model=Board,
    status_code=status.HTTP_201_CREATED,
)
def clone_board(
    board_id: UUID,
    body: CloneBody,
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("templates:write")),
) -> Board:
    """Clone columns of an existing board into a fresh board. Targets
    are NOT copied — per ADR 0017 cross-board model, the same target
    can appear on multiple boards via target_board_link rather than
    being duplicated.
    """
    require_role(user.role, "commander", action="clone board")
    src_row = session.get(BoardTable, board_id)
    if src_row is None or src_row.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="board not found")
    cols = session.exec(
        select(ColumnTable).where(ColumnTable.board_id == board_id).order_by(ColumnTable.order),  # type: ignore[arg-type]
    ).all()
    board = Board(
        name=body.name,
        transitions=src_row.transitions,
        theme=src_row.theme,
        columns=[
            Column(
                name=c.name,
                order=c.order,
                wip_limit=c.wip_limit,
                color=c.color,
                requires_approval=c.requires_approval,
            )
            for c in cols
        ],
    )
    repo.create_board(session, user.workspace_id, board)
    get_broker().publish(
        user.workspace_id,
        make_event(
            event_type="board.created",
            workspace_id=user.workspace_id,
            board_id=board.id,
            occurred_at=datetime.now(tz=UTC).isoformat(),
            data={
                "name": board.name,
                "theme": board.theme,
                "cloned_from": str(board_id),
            },
        ),
    )
    return board
