"""Repository functions — typed CRUD against the SQLModel tables.

Convert at the boundary between SQLModel rows (db side) and Pydantic
models (API side). Workflow logic lives elsewhere; these are pure data
operations.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlmodel import Session, select

from target_workspace.db.tables import (
    BoardTable,
    ColumnTable,
    PromotionPolicyTable,
    TargetTable,
    WorkspaceTable,
)
from target_workspace.db.track_correlation import (
    confidence_chain_projection,
    confidence_chain_projection_many,
)
from target_workspace.models.board import Board, Column
from target_workspace.models.promotion_policy import PromotionMode, PromotionPolicy
from target_workspace.models.target import Target


def now_utc() -> datetime:
    """Current UTC time. Centralized so the demo replay engine can inject a clock later."""
    return datetime.now(tz=UTC)


# ---------------------------------------------------------------------------
# Workspace
# ---------------------------------------------------------------------------


def create_workspace(session: Session, *, name: str) -> WorkspaceTable:
    row = WorkspaceTable(name=name, created_at=now_utc())
    session.add(row)
    session.flush()
    return row


def get_workspace(session: Session, workspace_id: UUID) -> WorkspaceTable | None:
    return session.get(WorkspaceTable, workspace_id)


# ---------------------------------------------------------------------------
# Board + Column
# ---------------------------------------------------------------------------


def create_board(session: Session, workspace_id: UUID, board: Board) -> BoardTable:
    row = BoardTable(
        id=board.id,
        workspace_id=workspace_id,
        name=board.name,
        transitions=board.transitions,
        theme=board.theme,
    )
    session.add(row)
    for col in board.columns:
        session.add(
            ColumnTable(
                id=col.id,
                board_id=board.id,
                name=col.name,
                order=col.order,
                wip_limit=col.wip_limit,
                color=col.color,
                requires_approval=col.requires_approval,
                expected_approving_roles=list(col.expected_approving_roles or []),
            )
        )
    session.flush()
    return row


def get_board(session: Session, board_id: UUID) -> Board | None:
    row = session.get(BoardTable, board_id)
    if row is None:
        return None
    cols = session.exec(select(ColumnTable).where(ColumnTable.board_id == board_id)).all()
    return Board(
        id=row.id,
        name=row.name,
        transitions=row.transitions,
        theme=row.theme,
        columns=[
            Column(
                id=c.id,
                name=c.name,
                order=c.order,
                wip_limit=c.wip_limit,
                color=c.color,
                requires_approval=c.requires_approval,
                expected_approving_roles=list(c.expected_approving_roles or []),
            )
            for c in cols
        ],
    )


def update_board(
    session: Session,
    board_id: UUID,
    *,
    name: str | None = None,
    theme: str | None = None,
    transitions: str | None = None,
) -> BoardTable | None:
    """Mutate board metadata in place. Column changes go through
    tw-itn — this function refuses to touch them. Returns None if the
    board doesn't exist."""
    row = session.get(BoardTable, board_id)
    if row is None:
        return None
    if name is not None:
        row.name = name
    if theme is not None:
        row.theme = theme
    if transitions is not None:
        row.transitions = transitions
    session.add(row)
    session.flush()
    return row


def board_target_count(session: Session, board_id: UUID) -> int:
    """How many targets live on a board. Used by delete_board to gate
    deletion of non-empty boards (safety per tw-cbz)."""
    from sqlalchemy import func  # noqa: PLC0415

    result = session.exec(
        select(func.count()).select_from(TargetTable).where(TargetTable.board_id == board_id),
    ).one()
    return int(result if isinstance(result, int) else result[0])


def delete_board(session: Session, board_id: UUID) -> bool:
    """Delete a board AND its columns. Refuses if any targets remain
    on the board — caller must move/delete targets first. Returns
    True on success, False if board not found, raises ValueError if
    non-empty."""
    row = session.get(BoardTable, board_id)
    if row is None:
        return False
    if board_target_count(session, board_id) > 0:
        msg = "board has targets; move or delete them before deleting the board"
        raise ValueError(msg)
    cols = session.exec(
        select(ColumnTable).where(ColumnTable.board_id == board_id),
    ).all()
    for c in cols:
        session.delete(c)
    session.flush()
    session.delete(row)
    session.flush()
    return True


def list_boards(session: Session, workspace_id: UUID) -> list[Board]:
    boards = session.exec(select(BoardTable).where(BoardTable.workspace_id == workspace_id)).all()
    return [b for b in (get_board(session, row.id) for row in boards) if b is not None]


# ---------------------------------------------------------------------------
# PromotionPolicy
# ---------------------------------------------------------------------------


def create_promotion_policy(
    session: Session, workspace_id: UUID, policy: PromotionPolicy
) -> PromotionPolicyTable:
    row = PromotionPolicyTable(
        id=policy.id,
        workspace_id=workspace_id,
        mode=policy.mode,
        min_confidence=policy.min_confidence,
        required_stages=[str(s) for s in policy.required_stages],
        approval_roles=list(policy.approval_roles),
        auto_publish_column_id=policy.auto_publish_column_id,
        on_low_confidence_route_to_column_id=policy.on_low_confidence_route_to_column_id,
    )
    session.add(row)
    session.flush()
    return row


def get_promotion_policy(session: Session, policy_id: UUID) -> PromotionPolicy | None:
    row = session.get(PromotionPolicyTable, policy_id)
    if row is None:
        return None
    mode_value: PromotionMode = row.mode  # type: ignore[assignment]
    return PromotionPolicy(
        id=row.id,
        mode=mode_value,
        min_confidence=row.min_confidence,
        required_stages=[UUID(s) for s in row.required_stages],
        approval_roles=list(row.approval_roles),
        auto_publish_column_id=row.auto_publish_column_id,
        on_low_confidence_route_to_column_id=row.on_low_confidence_route_to_column_id,
    )


# ---------------------------------------------------------------------------
# Target
# ---------------------------------------------------------------------------


def create_target(
    session: Session,
    workspace_id: UUID,
    board_id: UUID,
    column_id: UUID,
    target: Target,
) -> TargetTable:
    now = now_utc()
    row = TargetTable(
        id=target.id,
        workspace_id=workspace_id,
        board_id=board_id,
        column_id=column_id,
        name=target.name,
        cot_type=target.cot_type,
        category=target.category,
        lat=target.lat,
        lon=target.lon,
        hae=target.hae,
        ce=target.ce,
        le=target.le,
        time=target.time,
        stale=target.stale,
        confidence=target.confidence,
        version=target.version,
        remarks=target.remarks,
        source=target.source,
        geometry_kind=target.geometry_kind,
        geometry_quality=target.geometry_quality,
        ellipse=target.ellipse.model_dump() if target.ellipse is not None else None,
        polygon_vertices=(
            [list(v) for v in target.polygon_vertices]
            if target.polygon_vertices is not None
            else None
        ),
        custom_fields=dict(target.custom_fields),
        created_at=now,
        updated_at=now,
        position=_next_position_in_column(session, column_id),
    )
    session.add(row)
    session.flush()
    return row


def _next_position_in_column(session: Session, column_id: UUID) -> float:
    """Return a position value that lands a fresh target at the bottom
    of the column — current max position + 1, or 1.0 if the column is
    empty. Keeps drag-reorder math stable.
    """
    from sqlalchemy import func  # noqa: PLC0415

    result = session.exec(
        select(func.max(TargetTable.position)).where(
            TargetTable.column_id == column_id,
        ),
    ).one()
    # SQLAlchemy returns the raw scalar inside a 1-tuple for func.max;
    # SQLModel's typed select unwraps it. Be defensive in case the row
    # returns None (empty column).
    current_max = result if isinstance(result, int | float) else (result[0] if result else None)
    return (current_max if current_max is not None else 0.0) + 1.0


def get_target(session: Session, target_id: UUID) -> Target | None:
    row = session.get(TargetTable, target_id)
    if row is None:
        return None
    return _row_to_target(row, session=session)


def list_targets_on_board(session: Session, board_id: UUID) -> list[Target]:
    rows = session.exec(
        select(TargetTable)
        .where(TargetTable.board_id == board_id)
        .order_by(TargetTable.position, TargetTable.created_at),  # type: ignore[arg-type]
    ).all()
    chains = confidence_chain_projection_many(session, target_ids=[row.id for row in rows])
    return [_row_to_target(r, confidence_chain=chains.get(r.id)) for r in rows]


def list_targets_in_column(session: Session, column_id: UUID) -> list[Target]:
    rows = session.exec(
        select(TargetTable)
        .where(TargetTable.column_id == column_id)
        .order_by(TargetTable.position, TargetTable.created_at),  # type: ignore[arg-type]
    ).all()
    chains = confidence_chain_projection_many(session, target_ids=[row.id for row in rows])
    return [_row_to_target(r, confidence_chain=chains.get(r.id)) for r in rows]


def reorder_target(
    session: Session,
    target_id: UUID,
    column_id: UUID,
    after_id: UUID | None,
) -> TargetTable | None:
    """Reorder a target inside `column_id` so it lands immediately after
    `after_id` (or at the top of the column when after_id is None).

    Position values are floats; we insert as the midpoint between the
    chosen anchor and its next neighbour, so no other rows need to
    move. Eventually we'll re-normalize when midpoints get tiny — for
    now the float resolution is enough for thousands of inserts.
    """
    row = session.get(TargetTable, target_id)
    if row is None:
        return None
    # Order siblings (excluding the one we're moving) by current position.
    siblings = session.exec(
        select(TargetTable)
        .where(TargetTable.column_id == column_id)
        .where(TargetTable.id != target_id)
        .order_by(TargetTable.position, TargetTable.created_at),  # type: ignore[arg-type]
    ).all()
    if after_id is None:
        # Top of column.
        first_pos = siblings[0].position if siblings else 1.0
        new_pos = first_pos - 1.0
    else:
        anchor_index = next((i for i, s in enumerate(siblings) if s.id == after_id), None)
        if anchor_index is None:
            return None
        anchor = siblings[anchor_index]
        next_sibling = siblings[anchor_index + 1] if anchor_index + 1 < len(siblings) else None
        if next_sibling is None:
            new_pos = anchor.position + 1.0
        else:
            new_pos = (anchor.position + next_sibling.position) / 2.0
    row.column_id = column_id
    row.position = new_pos
    row.version += 1
    row.updated_at = now_utc()
    session.add(row)
    session.flush()
    return row


def move_target_to_column(
    session: Session, target_id: UUID, new_column_id: UUID
) -> TargetTable | None:
    row = session.get(TargetTable, target_id)
    if row is None:
        return None
    row.column_id = new_column_id
    row.version += 1
    row.updated_at = now_utc()
    session.add(row)
    session.flush()
    return row


# Fields a Target update is allowed to touch. column_id stays out of the
# allow-list — column transitions go through the workflow engine so the
# audit chain stays linear and approval gates aren't bypassed.
_TARGET_EDITABLE_FIELDS = frozenset(
    {
        "name",
        "cot_type",
        "category",
        "lat",
        "lon",
        "hae",
        "ce",
        "le",
        "time",
        "stale",
        "confidence",
        "remarks",
        "source",
        "geometry_kind",
        "geometry_quality",
        "ellipse",
        "polygon_vertices",
        "custom_fields",
    }
)


def update_target_fields(
    session: Session,
    target_id: UUID,
    changes: dict[str, Any],
) -> TargetTable | None:
    """Apply a partial-update dict to a Target row.

    `changes` is "only the keys the caller wants to write" — typically built
    from `pydantic.BaseModel.model_dump(exclude_unset=True)` on the request
    body. Unknown keys are silently ignored to keep callers tolerant of API
    schema growth, but they're checked against `_TARGET_EDITABLE_FIELDS` so
    workflow-controlled fields (column_id, version) cannot leak through.

    Returns the updated row, or None if the target_id is unknown. Caller
    should also bump the realtime broker with a target.updated event.
    """
    row = session.get(TargetTable, target_id)
    if row is None:
        return None
    touched = False
    for key, value in changes.items():
        if key not in _TARGET_EDITABLE_FIELDS:
            continue
        if key == "geometry_quality":
            custom_fields = dict(row.custom_fields or {})
            derivation = custom_fields.get("geometry_quality_derivation")
            derived = None
            if isinstance(derivation, dict):
                derived = derivation.get("derived")
            custom_fields["geometry_quality_override"] = {
                "value": value,
                "derived": derived or row.geometry_quality,
            }
            row.custom_fields = custom_fields
            row.geometry_quality = value
            touched = True
            continue
        # JSON columns (custom_fields, ellipse, polygon_vertices) — copy
        # so the row owns its own dict/list rather than aliasing the
        # caller's input.
        if key == "custom_fields" and value is not None:
            setattr(row, key, dict(value))
        elif key == "ellipse" and value is not None:
            # value may already be a dict (from PATCH) or an Ellipse Pydantic
            # model coming from create_target via _row_to_target round-trip.
            setattr(row, key, value.model_dump() if hasattr(value, "model_dump") else dict(value))
        elif key == "polygon_vertices" and value is not None:
            setattr(row, key, [list(v) for v in value])
        else:
            setattr(row, key, value)
        touched = True
    if not touched:
        return row
    row.version += 1
    row.updated_at = now_utc()
    session.add(row)
    session.flush()
    return row


def _row_to_target(
    row: TargetTable,
    *,
    session: Session | None = None,
    confidence_chain: list[dict[str, Any]] | None = None,
) -> Target:
    ellipse = None
    if row.ellipse:
        from target_workspace.models.target import Ellipse  # noqa: PLC0415

        ellipse = Ellipse(**row.ellipse)
    polygon_vertices = [list(v) for v in row.polygon_vertices] if row.polygon_vertices else None
    custom_fields = dict(row.custom_fields)
    custom_fields.pop("confidence_chain", None)
    if confidence_chain is not None:
        if confidence_chain:
            custom_fields["confidence_chain"] = confidence_chain
    elif session is not None:
        chain = confidence_chain_projection(session, target_id=row.id)
        if chain:
            custom_fields["confidence_chain"] = chain
    return Target(
        id=row.id,
        name=row.name,
        cot_type=row.cot_type,
        category=row.category,
        lat=row.lat,
        lon=row.lon,
        hae=row.hae,
        ce=row.ce,
        le=row.le,
        time=row.time,
        stale=row.stale,
        confidence=row.confidence,
        version=row.version,
        remarks=row.remarks,
        source=row.source,
        geometry_kind=row.geometry_kind,
        geometry_quality=row.geometry_quality,
        ellipse=ellipse,
        polygon_vertices=polygon_vertices,
        custom_fields=custom_fields,
        assigned_callsigns=list(row.assigned_callsigns or []),
    )
