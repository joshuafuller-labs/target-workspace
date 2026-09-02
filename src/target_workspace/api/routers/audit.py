"""/v1/audit — append-only event log query."""

from __future__ import annotations

import base64
import json
from datetime import datetime
from typing import Any
from uuid import UUID

from cryptography.exceptions import InvalidSignature
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, ConfigDict
from sqlmodel import Session, col, select

from target_workspace.api.dependencies import db_session, require_token_scope
from target_workspace.api.schemas import AuditEventOut
from target_workspace.api.signing import (
    GENESIS_PREV_HASH,
    audit_event_hash,
    canonical_payload,
    load_public,
)
from target_workspace.db.tables import AuditEventTable, InstanceIdentityTable, UserTable


def _encode_cursor(occurred_at: datetime, event_id: str) -> str:
    payload = json.dumps(
        {"t": occurred_at.isoformat(), "i": event_id},
        separators=(",", ":"),
    )
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        data = json.loads(raw)
        return datetime.fromisoformat(data["t"]), data["i"]
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"invalid cursor: {exc}",
        ) from exc


router = APIRouter(prefix="/v1/audit", tags=["audit"])


class AuditVerifyBreak(BaseModel):
    model_config = ConfigDict(extra="forbid")
    index: int
    event_id: UUID
    reason: str
    expected_prev_hash: str | None = None
    actual_prev_hash: str | None = None


class AuditVerifyOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ok: bool
    checked: int
    pre_chain_prefix: int = 0
    first_break: AuditVerifyBreak | None = None


def _parse_iso(s: str, *, field: str) -> datetime:
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"invalid {field}: {exc}",
        ) from exc
    return dt.replace(tzinfo=None) if dt.tzinfo else dt


def _apply_audit_filters(
    stmt: Any,
    *,
    workspace_id: UUID,
    target_id: UUID | None,
    actor_id: UUID | None,
    event_type: str | None,
    since: str | None,
    from_: str | None,
    to_: str | None,
    q: str | None,
) -> Any:
    stmt = stmt.where(AuditEventTable.workspace_id == workspace_id)
    if target_id is not None:
        stmt = stmt.where(AuditEventTable.target_id == target_id)
    if actor_id is not None:
        stmt = stmt.where(AuditEventTable.actor_id == actor_id)
    if event_type is not None:
        stmt = stmt.where(AuditEventTable.event_type == event_type)
    if since is not None:
        stmt = stmt.where(AuditEventTable.occurred_at > _parse_iso(since, field="since"))
    if from_ is not None:
        stmt = stmt.where(AuditEventTable.occurred_at >= _parse_iso(from_, field="from"))
    if to_ is not None:
        stmt = stmt.where(AuditEventTable.occurred_at <= _parse_iso(to_, field="to"))
    if q is not None:
        # SQLite has no JSON contains; the metadata_json column is plain
        # JSON text. LIKE against the serialized form is enough for the
        # 'find me events mentioning X' use case at MVP.
        from sqlalchemy import String, func  # noqa: PLC0415

        needle = f"%{q.lower()}%"
        stmt = stmt.where(
            func.lower(func.cast(col(AuditEventTable.metadata_json), String)).like(needle)
            | func.lower(AuditEventTable.justification).like(needle),
        )
    return stmt


@router.get("", response_model=list[AuditEventOut])
def list_audit_events(
    response: Response,
    target_id: UUID | None = Query(default=None),
    actor_id: UUID | None = Query(default=None),
    event_type: str | None = Query(default=None),
    since: str | None = Query(default=None),
    from_: str | None = Query(default=None, alias="from"),
    to_: str | None = Query(default=None, alias="to"),
    q: str | None = Query(default=None, max_length=200),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("audit:read")),
) -> list[AuditEventOut]:
    """Return audit events for this workspace; optionally filter by target.

    tw-cjk: pass `since=<iso-8601>` to resume a client sync.
    tw-13a: pass `cursor=<opaque>` to continue from a prior page.
            Response Link header carries rel="next" when more rows remain.
    tw-81p: actor_id / event_type / from / to / q for filtering.
    """
    stmt = select(AuditEventTable)
    stmt = _apply_audit_filters(
        stmt,
        workspace_id=user.workspace_id,
        target_id=target_id,
        actor_id=actor_id,
        event_type=event_type,
        since=since,
        from_=from_,
        to_=to_,
        q=q,
    )
    # tw-13a: cursor encodes the (occurred_at, id) of the LAST event of
    # the previous page; we want events strictly older.
    if cursor:
        cursor_t, _cursor_id = _decode_cursor(cursor)
        cursor_t_naive = cursor_t.replace(tzinfo=None) if cursor_t.tzinfo else cursor_t
        # Compound condition: occurred_at < cursor_t, OR equal with id < cursor_id.
        stmt = stmt.where(AuditEventTable.occurred_at < cursor_t_naive)
    stmt = stmt.order_by(AuditEventTable.occurred_at.desc()).limit(limit + 1)  # type: ignore[attr-defined]
    rows = session.exec(stmt).all()
    has_next = len(rows) > limit
    rows = rows[:limit]
    if has_next and rows:
        last = rows[-1]
        next_cursor = _encode_cursor(last.occurred_at, str(last.id))
        # Build the next URL referenced by the Link header.
        response.headers["Link"] = f'</v1/audit?limit={limit}&cursor={next_cursor}>; rel="next"'
    return [
        AuditEventOut(
            id=r.id,
            target_id=r.target_id,
            actor_id=r.actor_id,
            actor_kind=r.actor_kind,
            actor_ref=r.actor_ref,
            event_type=r.event_type,
            occurred_at=r.occurred_at,
            from_column_id=r.from_column_id,
            to_column_id=r.to_column_id,
            justification=r.justification,
            metadata=dict(r.metadata_json),
            peer_id=r.peer_id,
            prev_hash=r.prev_hash,
            signature=r.signature,
            signature_format_version=r.signature_format_version,
        )
        for r in rows
    ]


@router.get("/verify", response_model=AuditVerifyOut)
def verify_audit_chain(
    peer_id: UUID | None = Query(default=None),
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("audit:read")),
) -> AuditVerifyOut:
    stmt = (
        select(AuditEventTable)
        .where(AuditEventTable.workspace_id == user.workspace_id)
        .order_by(col(AuditEventTable.occurred_at).asc(), col(AuditEventTable.id).asc())
    )
    if peer_id is not None:
        stmt = stmt.where(AuditEventTable.peer_id == peer_id)
    rows = session.exec(stmt).all()
    expected_by_peer: dict[UUID, str] = {}
    pre_chain_open_by_peer: dict[UUID, bool] = {}
    public_by_peer: dict[UUID, Any] = {}
    checked = 0
    pre_chain_prefix = 0

    for row in rows:
        if row.peer_id is None or row.signature is None:
            return AuditVerifyOut(
                ok=False,
                checked=checked,
                first_break=AuditVerifyBreak(
                    index=checked,
                    event_id=row.id,
                    reason="missing_signature",
                ),
            )
        expected_prev_hash = expected_by_peer.get(row.peer_id, GENESIS_PREV_HASH)
        pre_chain_open = pre_chain_open_by_peer.get(row.peer_id, True)
        is_legacy_null_prefix = row.prev_hash is None and pre_chain_open
        if is_legacy_null_prefix:
            pre_chain_prefix += 1
        elif row.prev_hash != expected_prev_hash:
            return AuditVerifyOut(
                ok=False,
                checked=checked,
                pre_chain_prefix=pre_chain_prefix,
                first_break=AuditVerifyBreak(
                    index=checked,
                    event_id=row.id,
                    reason="broken_link",
                    expected_prev_hash=expected_prev_hash,
                    actual_prev_hash=row.prev_hash,
                ),
            )
        else:
            pre_chain_open_by_peer[row.peer_id] = False
        public_key = public_by_peer.get(row.peer_id)
        if public_key is None:
            identity = session.exec(
                select(InstanceIdentityTable).where(InstanceIdentityTable.peer_id == row.peer_id),
            ).first()
            if identity is None:
                return AuditVerifyOut(
                    ok=False,
                    checked=checked,
                    first_break=AuditVerifyBreak(
                        index=checked,
                        event_id=row.id,
                        reason="unknown_peer",
                    ),
                )
            public_key = load_public(identity)
            public_by_peer[row.peer_id] = public_key
        payload = canonical_payload(
            event_id=row.id,
            peer_id=row.peer_id,
            prev_hash=row.prev_hash,
            actor_id=row.actor_id,
            actor_kind=row.actor_kind,
            actor_ref=row.actor_ref,
            event_type=row.event_type,
            target_id=row.target_id,
            occurred_at_iso=row.occurred_at,
            metadata=row.metadata_json,
            signature_format_version=row.signature_format_version,
        )
        try:
            public_key.verify(base64.b64decode(row.signature), payload)
        except (InvalidSignature, ValueError):
            return AuditVerifyOut(
                ok=False,
                checked=checked,
                pre_chain_prefix=pre_chain_prefix,
                first_break=AuditVerifyBreak(
                    index=checked,
                    event_id=row.id,
                    reason="bad_signature",
                ),
            )
        expected_by_peer[row.peer_id] = audit_event_hash(
            event_id=row.id,
            peer_id=row.peer_id,
            prev_hash=row.prev_hash,
            actor_id=row.actor_id,
            actor_kind=row.actor_kind,
            actor_ref=row.actor_ref,
            event_type=row.event_type,
            target_id=row.target_id,
            occurred_at_iso=row.occurred_at,
            metadata=row.metadata_json,
            signature=row.signature,
            signature_format_version=row.signature_format_version,
        )
        checked += 1
    return AuditVerifyOut(ok=True, checked=checked, pre_chain_prefix=pre_chain_prefix)


@router.get("/export.csv")
def export_audit_csv(
    target_id: UUID | None = Query(default=None),
    actor_id: UUID | None = Query(default=None),
    event_type: str | None = Query(default=None),
    since: str | None = Query(default=None),
    from_: str | None = Query(default=None, alias="from"),
    to_: str | None = Query(default=None, alias="to"),
    q: str | None = Query(default=None, max_length=200),
    session: Session = Depends(db_session),
    user: UserTable = Depends(require_token_scope("audit:read")),
) -> Response:
    """CSV export of the filtered audit set. Capped at 10_000 rows.

    tw-81p: AAR / IO reporting export. Cap exists so a runaway filter
    can't try to materialize a million rows in one response.
    """
    import csv  # noqa: PLC0415
    import io  # noqa: PLC0415

    stmt = select(AuditEventTable)
    stmt = _apply_audit_filters(
        stmt,
        workspace_id=user.workspace_id,
        target_id=target_id,
        actor_id=actor_id,
        event_type=event_type,
        since=since,
        from_=from_,
        to_=to_,
        q=q,
    )
    stmt = stmt.order_by(AuditEventTable.occurred_at.desc()).limit(10_000)  # type: ignore[attr-defined]
    rows = session.exec(stmt).all()

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(
        [
            "id",
            "occurred_at",
            "event_type",
            "actor_id",
            "target_id",
            "from_column_id",
            "to_column_id",
            "justification",
            "metadata",
        ],
    )
    for r in rows:
        w.writerow(
            [
                str(r.id),
                r.occurred_at.isoformat() if r.occurred_at else "",
                r.event_type,
                str(r.actor_id) if r.actor_id else "",
                str(r.target_id) if r.target_id else "",
                str(r.from_column_id) if r.from_column_id else "",
                str(r.to_column_id) if r.to_column_id else "",
                r.justification or "",
                json.dumps(dict(r.metadata_json or {})),
            ],
        )
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="audit.csv"'},
    )
