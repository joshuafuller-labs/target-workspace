"""/v1/boards — Board CRUD + column CRUD (tw-itn)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session, select

from target_workspace.api.dependencies import db_session, require_token_scope
from target_workspace.api.rbac import require_role
from target_workspace.api.realtime import get_broker, make_event
from target_workspace.api.schemas import BoardCreate, BoardUpdate, ColumnIn
from target_workspace.db import repositories as repo
from target_workspace.db.tables import BoardTable, ColumnTable, TargetTable, UserTable
from target_workspace.models.board import Board, Column


class ColumnUpdate(BaseModel):
    """PATCH /v1/boards/{board_id}/columns/{column_id} — partial update."""

    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=80)
    order: int | None = Field(default=None, ge=0)
    wip_limit: int | None = Field(default=None, ge=1)
    color: str | None = Field(default=None, max_length=32)
    requires_approval: bool | None = None
    # tw-cck: dropdown hint list. Explicit-null clears.
    expected_approving_roles: list[str] | None = None


router = APIRouter(prefix="/v1/boards", tags=["boards"])


@router.post("", response_model=Board, status_code=status.HTTP_201_CREATED)
def create_board(
    body: BoardCreate,
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("boards:write")),
) -> Board:
    require_role(user.role, "commander", action="create board")
    board = Board(
        name=body.name,
        transitions=body.transitions,  # validated by Board
        theme=body.theme,
        columns=[
            Column(
                name=c.name,
                order=c.order,
                wip_limit=c.wip_limit,
                color=c.color,
                requires_approval=c.requires_approval,
                expected_approving_roles=list(c.expected_approving_roles or []),
            )
            for c in body.columns
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
            data={"name": board.name, "theme": board.theme},
        ),
    )
    return board


@router.get("", response_model=list[Board])
def list_boards(
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("boards:read")),
) -> list[Board]:
    return repo.list_boards(session, user.workspace_id)


@router.get("/{board_id}", response_model=Board)
def get_board(
    board_id: UUID,
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("boards:read")),
) -> Board:
    board = repo.get_board(session, board_id)
    if board is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="board not found")
    return board


@router.patch("/{board_id}", response_model=Board)
def patch_board(
    board_id: UUID,
    body: BoardUpdate,
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("boards:write")),
) -> Board:
    """Mutate board metadata (name / theme / transitions). Column
    add/edit/delete is tw-itn — out of scope here. Requires commander+
    because boards are workspace-shared state.
    """
    require_role(user.role, "commander", action="edit board")
    fields = body.model_dump(exclude_unset=True, exclude_none=True)
    if not fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="no fields to update",
        )
    row = repo.update_board(
        session,
        board_id,
        name=fields.get("name"),
        theme=fields.get("theme"),
        transitions=fields.get("transitions"),
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="board not found",
        )
    updated = repo.get_board(session, board_id)
    assert updated is not None
    get_broker().publish(
        user.workspace_id,
        make_event(
            event_type="board.updated",
            workspace_id=user.workspace_id,
            board_id=board_id,
            occurred_at=datetime.now(tz=UTC).isoformat(),
            data={"changed": sorted(fields.keys()), "actor": user.email},
        ),
    )
    return updated


@router.delete("/{board_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_board(
    board_id: UUID,
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("boards:write")),
) -> None:
    """Delete a board and its columns. Refuses if any targets remain
    (409 Conflict) — caller must move them first. Requires commander+.
    """
    require_role(user.role, "commander", action="delete board")
    try:
        ok = repo.delete_board(session, board_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="board not found",
        )
    get_broker().publish(
        user.workspace_id,
        make_event(
            event_type="board.deleted",
            workspace_id=user.workspace_id,
            board_id=board_id,
            occurred_at=datetime.now(tz=UTC).isoformat(),
            data={"actor": user.email},
        ),
    )


# ──────────────────────────────────────────────────────────────────────────
# Column CRUD — tw-itn
# ──────────────────────────────────────────────────────────────────────────


def _ensure_board(session: Session, board_id: UUID, workspace_id: UUID) -> None:
    # Use BoardTable (carries workspace_id) for the existence + tenancy check.
    # The domain Board model has no workspace_id, so the prior repo.get_board
    # check could not actually scope by workspace.
    board = session.get(BoardTable, board_id)
    if board is None or board.workspace_id != workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="board not found")


@router.post(
    "/{board_id}/columns",
    response_model=Column,
    status_code=status.HTTP_201_CREATED,
)
def add_column(
    board_id: UUID,
    body: ColumnIn,
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("boards:write")),
) -> Column:
    require_role(user.role, "commander", action="add column")
    from target_workspace.db.tables import BoardTable as _BoardTable  # noqa: PLC0415

    board_row = session.get(_BoardTable, board_id)
    if board_row is None or board_row.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="board not found")
    row = ColumnTable(
        id=uuid4(),
        board_id=board_id,
        name=body.name,
        order=body.order,
        wip_limit=body.wip_limit,
        color=body.color,
        requires_approval=body.requires_approval,
        expected_approving_roles=list(body.expected_approving_roles or []),
    )
    session.add(row)
    session.flush()
    get_broker().publish(
        user.workspace_id,
        make_event(
            event_type="board.updated",
            workspace_id=user.workspace_id,
            board_id=board_id,
            occurred_at=datetime.now(tz=UTC).isoformat(),
            data={"changed": ["columns"], "added": str(row.id), "actor": user.email},
        ),
    )
    return Column(
        id=row.id,
        name=row.name,
        order=row.order,
        wip_limit=row.wip_limit,
        color=row.color,
        requires_approval=row.requires_approval,
        expected_approving_roles=list(row.expected_approving_roles or []),
    )


@router.patch("/{board_id}/columns/{column_id}", response_model=Column)
def patch_column(
    board_id: UUID,
    column_id: UUID,
    body: ColumnUpdate,
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("boards:write")),
) -> Column:
    require_role(user.role, "commander", action="edit column")
    from target_workspace.db.tables import BoardTable as _BoardTable  # noqa: PLC0415

    board_row = session.get(_BoardTable, board_id)
    if board_row is None or board_row.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="board not found")
    row = session.get(ColumnTable, column_id)
    if row is None or row.board_id != board_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="column not found")
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="no fields to update",
        )
    for k, v in fields.items():
        setattr(row, k, v)
    session.add(row)
    session.flush()
    get_broker().publish(
        user.workspace_id,
        make_event(
            event_type="board.updated",
            workspace_id=user.workspace_id,
            board_id=board_id,
            occurred_at=datetime.now(tz=UTC).isoformat(),
            data={
                "changed": ["columns"],
                "edited": str(row.id),
                "fields": sorted(fields.keys()),
                "actor": user.email,
            },
        ),
    )
    return Column(
        id=row.id,
        name=row.name,
        order=row.order,
        wip_limit=row.wip_limit,
        color=row.color,
        requires_approval=row.requires_approval,
        expected_approving_roles=list(row.expected_approving_roles or []),
    )


@router.delete(
    "/{board_id}/columns/{column_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_column(
    board_id: UUID,
    column_id: UUID,
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("boards:write")),
) -> None:
    require_role(user.role, "commander", action="delete column")
    from target_workspace.db.tables import BoardTable as _BoardTable  # noqa: PLC0415

    board_row = session.get(_BoardTable, board_id)
    if board_row is None or board_row.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="board not found")
    row = session.get(ColumnTable, column_id)
    if row is None or row.board_id != board_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="column not found")
    # Refuse if any targets are still in this column.
    n_targets = session.exec(
        select(TargetTable).where(TargetTable.column_id == column_id),
    ).all()
    if n_targets:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"column has {len(n_targets)} target(s); move them first",
        )
    session.delete(row)
    session.flush()
    get_broker().publish(
        user.workspace_id,
        make_event(
            event_type="board.updated",
            workspace_id=user.workspace_id,
            board_id=board_id,
            occurred_at=datetime.now(tz=UTC).isoformat(),
            data={"changed": ["columns"], "removed": str(column_id), "actor": user.email},
        ),
    )


# ──────────────────────────────────────────────────────────────────────────
# tw-65l: atomic multi-column reorder
# ──────────────────────────────────────────────────────────────────────────


class _ReorderItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    order: int = Field(ge=0)


class _ReorderBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    columns: list[_ReorderItem]


@router.post("/{board_id}/columns/reorder", response_model=list[Column])
def reorder_columns(
    board_id: UUID,
    body: _ReorderBody,
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("boards:write")),
) -> list[Column]:
    """Atomic multi-column reorder. Per tw-65l.

    Body lists every column to reposition with its new order. Columns
    not in the body keep their current order — so the caller is
    responsible for sending a complete consistent assignment.
    """
    require_role(user.role, "commander", action="reorder columns")
    from target_workspace.db.tables import BoardTable as _BoardTable  # noqa: PLC0415

    board_row = session.get(_BoardTable, board_id)
    if board_row is None or board_row.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="board not found")

    # Resolve all rows up front; abort if any unknown column id.
    rows: list[ColumnTable] = []
    for item in body.columns:
        row = session.get(ColumnTable, item.id)
        if row is None or row.board_id != board_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"column not found: {item.id}",
            )
        rows.append(row)

    # Apply all updates in one flush.
    for item, row in zip(body.columns, rows, strict=True):
        row.order = item.order
        session.add(row)
    session.flush()

    refreshed = session.exec(
        select(ColumnTable).where(ColumnTable.board_id == board_id).order_by(ColumnTable.order),  # type: ignore[arg-type]
    ).all()

    get_broker().publish(
        user.workspace_id,
        make_event(
            event_type="board.updated",
            workspace_id=user.workspace_id,
            board_id=board_id,
            occurred_at=datetime.now(tz=UTC).isoformat(),
            data={
                "changed": ["columns"],
                "reordered": [str(r.id) for r in refreshed],
                "actor": user.email,
            },
        ),
    )
    return [
        Column(
            id=r.id,
            name=r.name,
            order=r.order,
            wip_limit=r.wip_limit,
            color=r.color,
            requires_approval=r.requires_approval,
        )
        for r in refreshed
    ]
