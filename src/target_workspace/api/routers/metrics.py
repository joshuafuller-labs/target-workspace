"""/v1/metrics — per-column dwell-time aggregations (tw-mwb).

Reads existing audit_event rows (target.moved + target.created) and
returns mean / p50 / p95 time-in-column, total counts. No new schema.

Computed on the fly per request — fine at MVP scale; materialized
rollups land in v1.x when board sizes hit O(10k) targets.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, col, select

from target_workspace.api.dependencies import db_session, require_token_scope
from target_workspace.db.tables import (
    AuditEventTable,
    BoardTable,
    ColumnTable,
    TargetTable,
    UserTable,
)

router = APIRouter(prefix="/v1/metrics", tags=["metrics"])


def _quantile(values: list[float], q: float) -> float | None:
    """Sorted-list quantile. Returns None for empty input."""
    if not values:
        return None
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    idx = q * (len(s) - 1)
    lo = int(idx)
    hi = min(lo + 1, len(s) - 1)
    frac = idx - lo
    return s[lo] * (1 - frac) + s[hi] * frac


def _to_naive_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(UTC).replace(tzinfo=None)


@router.get("/dwell")
def dwell_metrics(
    board_id: UUID = Query(...),
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("metrics:read")),
) -> dict[str, Any]:
    """Per-column dwell-time histogram for the given board.

    Output:
      {
        total_targets: int,
        total_audit_events: int,
        columns: [
          {
            id, name, order,
            current_count: int,
            dwell_seconds: { mean, p50, p95, count }
          }, ...
        ]
      }

    'Dwell' for a column = seconds between target.created/.moved INTO
    that column and the next .moved OUT (or 'now' if still there).
    """
    board = session.get(BoardTable, board_id)
    if board is None or board.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="board not found")

    columns = session.exec(
        select(ColumnTable).where(ColumnTable.board_id == board_id).order_by(ColumnTable.order),  # type: ignore[arg-type]
    ).all()
    {str(c.id): c for c in columns}

    targets = session.exec(
        select(TargetTable).where(TargetTable.board_id == board_id),
    ).all()
    total_targets = len(targets)

    # Pull moves for these targets, ordered chronologically per target.
    target_ids = {t.id for t in targets}
    audit_rows: Sequence[AuditEventTable] = []
    if target_ids:
        audit_rows = session.exec(
            select(AuditEventTable)
            .where(AuditEventTable.workspace_id == user.workspace_id)
            .where(col(AuditEventTable.target_id).in_(target_ids))
            .where(
                col(AuditEventTable.event_type).in_(
                    ["target.moved", "transitioned", "target.created"]
                )
            )
            .order_by(col(AuditEventTable.occurred_at).asc()),
        ).all()

    # Compute dwell per (target, column) span.
    dwell_by_col: dict[str, list[float]] = {str(c.id): [] for c in columns}
    now_naive = _to_naive_utc(datetime.now(tz=UTC))
    by_target: dict[str, list[AuditEventTable]] = {}
    for ev in audit_rows:
        by_target.setdefault(str(ev.target_id), []).append(ev)
    for events in by_target.values():
        # State: current_column_id + entered_at
        cur_col: str | None = None
        entered_at: datetime | None = None
        for ev in events:
            # Try to_column_id; if absent, this isn't a move — skip.
            to_col = str(ev.to_column_id) if ev.to_column_id else None
            ts = _to_naive_utc(ev.occurred_at)
            if cur_col is not None and entered_at is not None:
                duration = (ts - entered_at).total_seconds()
                if duration >= 0:
                    dwell_by_col.setdefault(cur_col, []).append(duration)
            cur_col = to_col
            entered_at = ts
        # Final span: still-in-column → now
        if cur_col is not None and entered_at is not None:
            duration = (now_naive - entered_at).total_seconds()
            if duration >= 0:
                dwell_by_col.setdefault(cur_col, []).append(duration)

    current_counts = {str(c.id): 0 for c in columns}
    for t in targets:
        if str(t.column_id) in current_counts:
            current_counts[str(t.column_id)] += 1

    out_columns: list[dict[str, Any]] = []
    for c in columns:
        bucket = dwell_by_col.get(str(c.id), [])
        out_columns.append(
            {
                "id": str(c.id),
                "name": c.name,
                "order": c.order,
                "current_count": current_counts.get(str(c.id), 0),
                "dwell_seconds": {
                    "mean": (sum(bucket) / len(bucket)) if bucket else None,
                    "p50": _quantile(bucket, 0.5),
                    "p95": _quantile(bucket, 0.95),
                    "count": len(bucket),
                },
            },
        )

    return {
        "total_targets": total_targets,
        "total_audit_events": len(audit_rows),
        "columns": out_columns,
    }
