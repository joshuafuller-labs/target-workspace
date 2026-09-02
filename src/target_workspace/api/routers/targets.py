"""/v1/targets — Target CRUD."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlmodel import Session, select

from target_workspace.api.dependencies import (
    current_user,
    db_session,
    enforce_token_scope,
)
from target_workspace.api.rbac import has_role, require_role
from target_workspace.api.realtime import get_broker, make_event
from target_workspace.api.schemas import (
    TargetCreate,
    TargetMove,
    TargetReorder,
    TargetUpdate,
)
from target_workspace.db import repositories as repo
from target_workspace.db.tables import (
    BoardTable,
    ColumnTable,
    TargetTable,
    TrackObservationTable,
    UserTable,
    WorkflowNominationTable,
)
from target_workspace.db.track_correlation import (
    append_observation,
    apply_initial_geometry_quality_derivation,
    find_matching_track,
)
from target_workspace.models.target import Target
from target_workspace.plugins.loader import (
    make_publisher_dispatcher,
    register_builtin_plugins,
)
from target_workspace.workflow import (
    MoveRequested,
    PromotionDenied,
    approve_nomination,
    evaluate,
    record_event,
    reject_nomination,
    transition_target,
)

router = APIRouter(prefix="/v1/targets", tags=["targets"])

# Ensure first-party plugins are loaded before any dispatch.
register_builtin_plugins()
_dispatcher = make_publisher_dispatcher()


class MovePreviewOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    verdict: str
    reason: str
    proposed_by: str
    evidence: dict[str, Any]
    target_id: UUID | None = None
    to_column_id: UUID | None = None
    approver_role: str | None = None


class NominationResolveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    justification: str | None = Field(default=None, max_length=2000)


class NominationRejectOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str
    nomination_id: UUID


@router.post("", response_model=Target, status_code=status.HTTP_201_CREATED)
def create_target(
    body: TargetCreate,
    request: Request,
    session: Session = Depends(db_session),
    user: UserTable = Depends(current_user),
) -> Target:
    enforce_token_scope(request, "targets:write", f"targets:write:board:{body.board_id}")
    require_role(user.role, "observer", action="create target")
    board = repo.get_board(session, body.board_id)
    if board is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="board not found")
    if body.column_id not in {c.id for c in board.columns}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="column_id does not belong to board_id",
        )
    from target_workspace.models.target import Ellipse  # noqa: PLC0415

    target = Target(
        name=body.name,
        cot_type=body.cot_type,
        category=body.category,
        lat=body.lat,
        lon=body.lon,
        hae=body.hae,
        ce=body.ce,
        le=body.le,
        time=body.time,
        stale=body.stale,
        confidence=body.confidence,
        remarks=body.remarks,
        source=body.source,
        geometry_kind=body.geometry_kind,
        geometry_quality=body.geometry_quality,
        ellipse=Ellipse(**body.ellipse.model_dump()) if body.ellipse else None,
        polygon_vertices=body.polygon_vertices,
        custom_fields=body.custom_fields,
    )
    apply_initial_geometry_quality_derivation(target)
    # Correlate against an existing track before creating a new row. Per
    # the Ukraine audit (§1), re-observations of the same physical
    # contact should fold into one persistent target, not multiply.
    matched = find_matching_track(
        session,
        workspace_id=user.workspace_id,
        board_id=body.board_id,
        candidate=target,
    )
    if matched is not None:
        append_observation(
            session,
            workspace_id=user.workspace_id,
            target_row=matched,
            candidate=target,
        )
        session.flush()
        updated = repo.get_target(session, matched.id)
        assert updated is not None
        get_broker().publish(
            user.workspace_id,
            make_event(
                event_type="target.updated",
                workspace_id=user.workspace_id,
                board_id=matched.board_id,
                target_id=updated.id,
                occurred_at=target.time.isoformat(),
                data={
                    "changed": [
                        "lat",
                        "lon",
                        "time",
                        "observation_count",
                        "geometry_quality",
                    ],
                    "version": updated.version,
                    "merged_from": "observation",
                },
            ),
        )
        return updated

    repo.create_target(session, user.workspace_id, body.board_id, body.column_id, target)
    # Seed the observation log with the initial fix.
    from datetime import UTC  # noqa: PLC0415
    from datetime import datetime as _dt  # noqa: PLC0415
    from uuid import uuid4 as _uuid4  # noqa: PLC0415

    session.add(
        TrackObservationTable(
            id=_uuid4(),
            workspace_id=user.workspace_id,
            target_id=target.id,
            observed_at=target.time,
            lat=target.lat,
            lon=target.lon,
            hae=target.hae,
            ce=target.ce,
            confidence=target.confidence,
            source=target.source,
            classification=None,
            created_at=_dt.now(tz=UTC),
        ),
    )
    get_broker().publish(
        user.workspace_id,
        make_event(
            event_type="target.created",
            workspace_id=user.workspace_id,
            board_id=body.board_id,
            target_id=target.id,
            occurred_at=target.time.isoformat(),
            data={"column_id": str(body.column_id), "name": target.name},
        ),
    )
    # tw-50i5: fan to publishers whose column_filter_ids includes the
    # initial column. Mirrors the publisher dispatch already present on
    # transition_target. Best-effort — publisher failures are not
    # creation-fatal.
    from sqlmodel import select as _select  # noqa: PLC0415

    from target_workspace.db.tables import PublisherConfigTable  # noqa: PLC0415

    col_str = str(body.column_id)
    pubs = session.exec(
        _select(PublisherConfigTable).where(
            PublisherConfigTable.workspace_id == user.workspace_id,
            PublisherConfigTable.enabled == True,  # noqa: E712
        ),
    ).all()
    for p in pubs:
        if col_str in p.column_filter_ids:
            cfg = dict(p.adapter_config)
            cfg.setdefault("board_id", str(body.board_id))
            try:
                _dispatcher(
                    publisher_id=p.id,
                    plugin_type=p.plugin_type,
                    adapter_config=cfg,
                    target=target,
                )
            except Exception:
                import logging  # noqa: PLC0415

                logging.getLogger(__name__).warning(
                    "publisher %s dispatch failed on target.created",
                    p.name,
                )
    return target


# ── tw-j3x6: bulk import ─────────────────────────────────────────────


class _BulkRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)
    remarks: str | None = Field(default=None, max_length=4000)
    cot_type: str | None = Field(default=None, min_length=1)


class _BulkIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    board_id: UUID
    column_id: UUID
    rows: list[dict[str, Any]] = Field(min_length=1, max_length=1000)


@router.post("/bulk", status_code=status.HTTP_201_CREATED)
def bulk_create(
    body: _BulkIn,
    request: Request,
    session: Session = Depends(db_session),
    user: UserTable = Depends(current_user),
) -> dict[str, Any]:
    """Create many targets in one POST. Per-row outcomes returned.

    Per-row validation errors don't fail the whole request — the client
    can re-submit the rejected rows after fixing them. Aggregate audit
    event ('bulk_imported') ships in a separate ticket.
    """
    enforce_token_scope(request, "targets:write", f"targets:write:board:{body.board_id}")
    require_role(user.role, "observer", action="bulk create targets")
    board = repo.get_board(session, body.board_id)
    if board is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="board not found")
    if body.column_id not in {c.id for c in board.columns}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="column_id does not belong to board_id",
        )
    from datetime import UTC  # noqa: PLC0415
    from datetime import datetime as _dt  # noqa: PLC0415

    from pydantic import ValidationError  # noqa: PLC0415

    now = _dt.now(tz=UTC)
    out_rows: list[dict[str, Any]] = []
    for row in body.rows:
        try:
            parsed = _BulkRow.model_validate(row)
        except ValidationError as exc:
            out_rows.append({"ok": False, "error": str(exc.errors()[0]["msg"]), "input": row})
            continue
        target_create = TargetCreate(
            board_id=body.board_id,
            column_id=body.column_id,
            name=parsed.name,
            cot_type=parsed.cot_type or "a-u-G",
            lat=parsed.lat,
            lon=parsed.lon,
            time=now,
            remarks=parsed.remarks,
            custom_fields={},
        )
        try:
            created = create_target(
                body=target_create,
                request=request,
                session=session,
                user=user,
            )
            out_rows.append({"ok": True, "id": str(created.id), "name": created.name})
        except HTTPException as exc:
            out_rows.append({"ok": False, "error": str(exc.detail), "input": row})
    return {"rows": out_rows}


# ── tw-5kqh: assign / unassign callsigns ─────────────────────────────


class _CallsignBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    callsign: str = Field(min_length=1, max_length=64)


@router.post("/{target_id}/assign", response_model=Target)
def assign_callsign(
    target_id: UUID,
    body: _CallsignBody,
    request: Request,
    session: Session = Depends(db_session),
    user: UserTable = Depends(current_user),
) -> Target:
    """Add a callsign to target.assigned_callsigns. Idempotent.

    tw-5kqh: free-form string at MVP. Validation against a roster lives
    behind tw-tl9r (user-callsign mapping) in v1.x.
    """
    require_role(user.role, "operator", action="assign callsign")
    row = session.get(TargetTable, target_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="target not found")
    if row.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="target not found")
    enforce_token_scope(request, "targets:write", f"targets:write:board:{row.board_id}")
    callsigns = list(row.assigned_callsigns or [])
    if body.callsign not in callsigns:
        callsigns.append(body.callsign)
        row.assigned_callsigns = callsigns
        session.add(row)
        session.flush()
    refreshed = repo.get_target(session, target_id)
    assert refreshed is not None
    return refreshed


@router.post("/{target_id}/unassign", response_model=Target)
def unassign_callsign(
    target_id: UUID,
    body: _CallsignBody,
    request: Request,
    session: Session = Depends(db_session),
    user: UserTable = Depends(current_user),
) -> Target:
    """Remove a callsign from target.assigned_callsigns. Idempotent
    (removing an already-absent callsign returns 200, not 404)."""
    require_role(user.role, "operator", action="unassign callsign")
    row = session.get(TargetTable, target_id)
    if row is None or row.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="target not found")
    enforce_token_scope(request, "targets:write", f"targets:write:board:{row.board_id}")
    callsigns = [c for c in (row.assigned_callsigns or []) if c != body.callsign]
    if callsigns != list(row.assigned_callsigns or []):
        row.assigned_callsigns = callsigns
        session.add(row)
        session.flush()
    refreshed = repo.get_target(session, target_id)
    assert refreshed is not None
    return refreshed


# ── tw-b43: Attachment refs ──────────────────────────────────────────


ATTACHMENT_KINDS = {"image", "document", "osint-link", "video", "other"}


class _AttachmentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: str
    url: str = Field(min_length=1, max_length=2000)
    sha256: str | None = Field(default=None, max_length=64)
    media_type: str | None = Field(default=None, max_length=100)
    caption: str | None = Field(default=None, max_length=500)


@router.post("/{target_id}/attachments", response_model=Target)
def add_attachment(
    target_id: UUID,
    body: _AttachmentBody,
    request: Request,
    session: Session = Depends(db_session),
    user: UserTable = Depends(current_user),
) -> Target:
    """Append a URL/hash reference to target.custom_fields['attachments']."""
    require_role(user.role, "operator", action="add attachment")
    if body.kind not in ATTACHMENT_KINDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"kind must be one of {sorted(ATTACHMENT_KINDS)}",
        )
    row = session.get(TargetTable, target_id)
    if row is None or row.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="target not found")
    enforce_token_scope(request, "targets:write", f"targets:write:board:{row.board_id}")
    new_custom = dict(row.custom_fields or {})
    atts = list(new_custom.get("attachments") or [])
    atts.append(body.model_dump())
    new_custom["attachments"] = atts
    row.custom_fields = new_custom
    session.add(row)
    session.flush()
    refreshed = repo.get_target(session, target_id)
    assert refreshed is not None
    return refreshed


@router.delete("/{target_id}/attachments/{idx}", response_model=Target)
def remove_attachment(
    target_id: UUID,
    idx: int,
    request: Request,
    session: Session = Depends(db_session),
    user: UserTable = Depends(current_user),
) -> Target:
    """Remove an attachment by zero-based index."""
    require_role(user.role, "operator", action="remove attachment")
    row = session.get(TargetTable, target_id)
    if row is None or row.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="target not found")
    enforce_token_scope(request, "targets:write", f"targets:write:board:{row.board_id}")
    new_custom = dict(row.custom_fields or {})
    atts = list(new_custom.get("attachments") or [])
    if idx < 0 or idx >= len(atts):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="attachment index out of range",
        )
    atts.pop(idx)
    new_custom["attachments"] = atts
    row.custom_fields = new_custom
    session.add(row)
    session.flush()
    refreshed = repo.get_target(session, target_id)
    assert refreshed is not None
    return refreshed


# ── tw-fgz: FEMA PDA damage assessment ───────────────────────────────


DAMAGE_TIERS = {"affected", "minor", "major", "destroyed"}
STRUCTURE_TYPES = {"residential", "commercial", "critical-infra", "agricultural", "other"}
OCCUPANCY_VALUES = {"occupied", "vacant", "unknown"}


class _DamageAssessmentBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    address: str = Field(min_length=1, max_length=500)
    structure_type: str
    occupancy: str
    damage_tier: str
    owner_contact: str | None = Field(default=None, max_length=500)
    photo_refs: list[str] | None = None
    notes: str | None = Field(default=None, max_length=4000)


@router.post("/{target_id}/damage-assessment", response_model=Target)
def post_damage_assessment(
    target_id: UUID,
    body: _DamageAssessmentBody,
    request: Request,
    session: Session = Depends(db_session),
    user: UserTable = Depends(current_user),
) -> Target:
    """Attach FEMA-aligned Preliminary Damage Assessment data to a target.

    Stored on target.custom_fields['damage_assessment'] so a v1.x
    aggregation can roll up multiple structures for PA / IA submission.
    """
    from datetime import UTC as _UTC2  # noqa: PLC0415
    from datetime import datetime as _dt2  # noqa: PLC0415

    require_role(user.role, "operator", action="record damage assessment")
    if body.damage_tier not in DAMAGE_TIERS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"damage_tier must be one of {sorted(DAMAGE_TIERS)}",
        )
    if body.structure_type not in STRUCTURE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"structure_type must be one of {sorted(STRUCTURE_TYPES)}",
        )
    if body.occupancy not in OCCUPANCY_VALUES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"occupancy must be one of {sorted(OCCUPANCY_VALUES)}",
        )

    row = session.get(TargetTable, target_id)
    if row is None or row.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="target not found")
    enforce_token_scope(request, "targets:write", f"targets:write:board:{row.board_id}")

    pda = body.model_dump()
    pda["assessed_by"] = str(user.id)
    pda["assessed_at"] = _dt2.now(tz=_UTC2).isoformat().replace("+00:00", "Z")

    new_custom = dict(row.custom_fields or {})
    new_custom["damage_assessment"] = pda
    row.custom_fields = new_custom
    session.add(row)
    session.flush()

    refreshed = repo.get_target(session, target_id)
    assert refreshed is not None
    return refreshed


# ── tw-fnrv: auto-ETA per assignee ───────────────────────────────────

import math as _math  # noqa: E402


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in meters."""
    r = 6_371_000.0
    p1 = _math.radians(lat1)
    p2 = _math.radians(lat2)
    dp = _math.radians(lat2 - lat1)
    dl = _math.radians(lon2 - lon1)
    a = _math.sin(dp / 2) ** 2 + _math.cos(p1) * _math.cos(p2) * _math.sin(dl / 2) ** 2
    return 2 * r * _math.asin(_math.sqrt(a))


@router.get("/{target_id}/eta")
def target_eta(
    target_id: UUID,
    request: Request,
    session: Session = Depends(db_session),
    user: UserTable = Depends(current_user),
) -> list[dict[str, Any]]:
    """For each assignee callsign on this target, estimate time-to-arrive
    from PLI cache. Per tw-fnrv.

    Returns list of {callsign, status, distance_m?, eta_seconds?}:
      offline    — callsign not in PLI cache
      stationary — speed = 0
      closing    — speed > 0 (distance / speed)
    """
    from target_workspace.api.presence import lookup as _lookup  # noqa: PLC0415

    row = session.get(TargetTable, target_id)
    if row is None or row.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="target not found")
    enforce_token_scope(request, "targets:read", f"targets:read:board:{row.board_id}")

    out: list[dict[str, Any]] = []
    for callsign in row.assigned_callsigns or []:
        entry = _lookup(callsign)
        if entry is None:
            out.append(
                {
                    "callsign": callsign,
                    "status": "offline",
                    "distance_m": None,
                    "eta_seconds": None,
                },
            )
            continue
        distance = _haversine_m(entry.lat, entry.lon, row.lat, row.lon)
        speed = entry.speed
        if speed is None or speed <= 0.0:
            status_str = "stationary"
            eta_seconds = None
        else:
            status_str = "closing"
            eta_seconds = distance / speed
        out.append(
            {
                "callsign": callsign,
                "status": status_str,
                "distance_m": distance,
                "eta_seconds": eta_seconds,
            },
        )
    return out


@router.get("/{target_id}/observations")
def list_observations(
    target_id: UUID,
    request: Request,
    session: Session = Depends(db_session),
    user: UserTable = Depends(current_user),
) -> list[dict[str, Any]]:
    """Return the append-only observation log for a Target — every
    sensor hit, oldest to newest. Useful for analysts following a track
    refinement and for auditing the source chain of an engagement."""
    from sqlmodel import select  # noqa: PLC0415

    target_row = session.get(TargetTable, target_id)
    if target_row is None or target_row.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="target not found")
    enforce_token_scope(request, "targets:read", f"targets:read:board:{target_row.board_id}")

    rows = session.exec(
        select(TrackObservationTable)
        .where(TrackObservationTable.target_id == target_id)
        .where(TrackObservationTable.workspace_id == user.workspace_id)
        .order_by(TrackObservationTable.observed_at),  # type: ignore[arg-type]
    ).all()
    return [
        {
            "id": str(r.id),
            "observed_at": r.observed_at.isoformat(),
            "lat": r.lat,
            "lon": r.lon,
            "hae": r.hae,
            "ce": r.ce,
            "confidence": r.confidence,
            "source": r.source,
            "classification": r.classification,
        }
        for r in rows
    ]


@router.post("/{target_id}/move/preview", response_model=MovePreviewOut)
def preview_move_target(
    target_id: UUID,
    body: TargetMove,
    request: Request,
    session: Session = Depends(db_session),
    user: UserTable = Depends(current_user),
) -> MovePreviewOut:
    """Evaluate a target move without applying side effects."""
    require_role(user.role, "operator", action="preview target move")
    target_row = session.get(TargetTable, target_id)
    if target_row is None or target_row.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="target not found")
    enforce_token_scope(request, "targets:read", f"targets:read:board:{target_row.board_id}")
    decision = evaluate(
        session,
        MoveRequested(
            target_id=target_id,
            to_column_id=body.column_id,
            actor_id=user.id,
            justification=body.justification,
            approving_role=body.approving_role,
        ),
    )
    return MovePreviewOut(
        verdict=decision.verdict,
        reason=decision.reason,
        proposed_by=decision.proposed_by,
        evidence=dict(decision.evidence),
        target_id=decision.target_id,
        to_column_id=decision.to_column_id,
        approver_role=decision.approver_role,
    )


@router.post("/nominations/{nomination_id}/approve", response_model=Target)
def approve_target_nomination(
    nomination_id: UUID,
    body: NominationResolveIn,
    request: Request,
    session: Session = Depends(db_session),
    user: UserTable = Depends(current_user),
) -> Target:
    require_role(user.role, "approver", action="approve workflow nomination")
    nomination = session.get(WorkflowNominationTable, nomination_id)
    if nomination is None or nomination.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="nomination not found")
    target_row = session.get(TargetTable, nomination.target_id)
    if target_row is None or target_row.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="target not found")
    enforce_token_scope(request, "targets:write", f"targets:write:board:{target_row.board_id}")
    try:
        result = approve_nomination(
            session,
            nomination_id=nomination_id,
            actor_id=user.id,
            justification=body.justification,
            publisher_dispatch=_dispatcher,
        )
    except PromotionDenied as exc:
        if "not found" in str(exc):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    audit = result.event
    target_row = session.get(TargetTable, audit.target_id)
    get_broker().publish(
        user.workspace_id,
        make_event(
            event_type="target.moved",
            workspace_id=user.workspace_id,
            board_id=target_row.board_id if target_row is not None else None,
            target_id=audit.target_id,
            occurred_at=audit.occurred_at.isoformat(),
            data={
                "from_column_id": str(audit.from_column_id) if audit.from_column_id else None,
                "to_column_id": str(audit.to_column_id) if audit.to_column_id else None,
                "justification": audit.justification,
                "nomination_id": str(nomination_id),
            },
        ),
    )
    return result.target


@router.post("/nominations/{nomination_id}/reject", response_model=NominationRejectOut)
def reject_target_nomination(
    nomination_id: UUID,
    body: NominationResolveIn,
    request: Request,
    session: Session = Depends(db_session),
    user: UserTable = Depends(current_user),
) -> NominationRejectOut:
    require_role(user.role, "approver", action="reject workflow nomination")
    nomination = session.get(WorkflowNominationTable, nomination_id)
    if nomination is None or nomination.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="nomination not found")
    target_row = session.get(TargetTable, nomination.target_id)
    if target_row is None or target_row.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="target not found")
    enforce_token_scope(request, "targets:write", f"targets:write:board:{target_row.board_id}")
    try:
        reject_nomination(
            session,
            nomination_id=nomination_id,
            actor_id=user.id,
            justification=body.justification,
        )
    except PromotionDenied as exc:
        if "not found" in str(exc):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return NominationRejectOut(status="rejected", nomination_id=nomination_id)


@router.get("", response_model=list[Target])
def list_targets(
    request: Request,
    board_id: UUID = Query(),
    column_id: UUID | None = Query(default=None),
    session: Session = Depends(db_session),
    user: UserTable = Depends(current_user),
) -> list[Target]:
    enforce_token_scope(request, "targets:read", f"targets:read:board:{board_id}")
    board = session.get(BoardTable, board_id)
    if board is None or board.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="board not found")
    if column_id is not None:
        column = session.get(ColumnTable, column_id)
        if column is None or column.board_id != board_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="column_id does not belong to board_id",
            )
        return repo.list_targets_in_column(session, column_id)
    return repo.list_targets_on_board(session, board_id)


@router.get("/{target_id}", response_model=Target)
def get_target(
    target_id: UUID,
    request: Request,
    response: Response,
    session: Session = Depends(db_session),
    user: UserTable = Depends(current_user),
) -> Target:
    row = session.get(TargetTable, target_id)
    if row is None or row.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="target not found")
    enforce_token_scope(request, "targets:read", f"targets:read:board:{row.board_id}")
    target = repo.get_target(session, target_id)
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="target not found")
    # tw-2j9: ETag exposes the monotonic version for offline-first sync.
    response.headers["ETag"] = f'W/"v{target.version}"'
    return target


@router.patch("/{target_id}", response_model=Target)
def update_target(
    target_id: UUID,
    body: TargetUpdate,
    request: Request,
    response: Response,
    session: Session = Depends(db_session),
    user: UserTable = Depends(current_user),
) -> Target:
    """Partial-update human-authored fields on a Target.

    Workflow-relevant changes (column transitions) go through `/move`.
    This endpoint is for the "edit metadata" path — typo fix, CoT-type
    affiliation flip, attribution correction, operator note. Every edit
    bumps `version` and fans out as a `target.updated` realtime event.
    """
    require_role(user.role, "operator", action="edit target metadata")
    fields = body.model_dump(exclude_unset=True)
    if not fields:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="no fields to update",
        )
    # Snapshot the BEFORE state so the audit event can record from→to for
    # changed fields without re-deriving them later. Stringify so the JSON
    # column accepts UUIDs/datetimes uniformly.
    pre = repo.get_target(session, target_id)
    if pre is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="target not found")
    pre_row = session.get(TargetTable, target_id)
    if pre_row is None or pre_row.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="target not found")
    enforce_token_scope(request, "targets:write", f"targets:write:board:{pre_row.board_id}")
    # tw-2j9: optimistic concurrency via If-Match. Absent header = no
    # check (back-compat). Header format: W/"v<version>".
    if_match = request.headers.get("If-Match")
    if if_match:
        expected = f'W/"v{pre.version}"'
        if if_match != expected:
            raise HTTPException(
                status_code=status.HTTP_412_PRECONDITION_FAILED,
                detail=f"version mismatch (expected {expected}, got {if_match})",
            )
    row = repo.update_target_fields(session, target_id, fields)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="target not found")
    updated = repo.get_target(session, target_id)
    assert updated is not None  # row was just present
    # Append an actor-attributed audit event for the edit. Every changed
    # field gets a from/to record so the audit trail tells you WHO made
    # WHAT change, not just that the row mutated.
    diff: dict[str, dict[str, Any]] = {}
    pre_dump = pre.model_dump()
    post_dump = updated.model_dump()
    for key in fields:
        before = pre_dump.get(key)
        after = post_dump.get(key)
        if before != after:
            diff[key] = {"from": _jsonable(before), "to": _jsonable(after)}
    record_event(
        session,
        workspace_id=user.workspace_id,
        target_id=target_id,
        actor_id=user.id,
        event_type="updated",
        justification=f"edited via PATCH by {user.email}",
        metadata={"diff": diff, "version": updated.version},
    )
    get_broker().publish(
        user.workspace_id,
        make_event(
            event_type="target.updated",
            workspace_id=user.workspace_id,
            board_id=row.board_id,
            target_id=updated.id,
            occurred_at=row.updated_at.isoformat(),
            data={
                "changed": sorted(diff.keys()),
                "version": updated.version,
                "actor": user.email,
            },
        ),
    )
    response.headers["ETag"] = f'W/"v{updated.version}"'
    return updated


def _jsonable(value: Any) -> Any:
    """Best-effort coerce a Target field value to a JSON-storable shape."""
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, list):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    # datetimes, UUIDs, etc. → string
    return str(value)


@router.post("/{target_id}/move", response_model=Target)
def move_target(
    target_id: UUID,
    body: TargetMove,
    request: Request,
    session: Session = Depends(db_session),
    user: UserTable = Depends(current_user),
) -> Target:
    """Promote a Target into another column.

    Routes through the workflow engine: validates against Board rules,
    enforces approval-required gates, writes an AuditEvent, and dispatches
    any matched Publishers.

    Authorization: any operator+ can move cards between non-gated columns.
    Approval-gated columns additionally require the caller to be approver+.
    """
    require_role(user.role, "operator", action="move target")
    target_row_pre = session.get(TargetTable, target_id)
    if target_row_pre is not None and target_row_pre.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="target not found")
    if target_row_pre is not None:
        enforce_token_scope(
            request,
            "targets:write",
            f"targets:write:board:{target_row_pre.board_id}",
        )
        target_board = repo.get_board(session, target_row_pre.board_id)
        if target_board is not None:
            dest = next(
                (c for c in target_board.columns if c.id == body.column_id),
                None,
            )
            # tw-5i2: soft WIP-limit. Block by default; X-Wip-Override: true
            # bypasses with the override recorded in the audit metadata
            # (the workflow engine records justification verbatim).
            if (
                dest is not None
                and dest.wip_limit is not None
                and dest.id != target_row_pre.column_id  # exempt no-op move
            ):
                current_count = len(
                    session.exec(
                        select(TargetTable).where(TargetTable.column_id == dest.id),
                    ).all(),
                )
                if current_count >= dest.wip_limit:
                    override = request.headers.get("X-Wip-Override", "").lower() == "true"
                    if not override:
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail=(
                                f"column '{dest.name}' at WIP limit "
                                f"({current_count}/{dest.wip_limit}); "
                                "resubmit with X-Wip-Override: true to bypass"
                            ),
                        )
            if dest is not None and dest.requires_approval and not has_role(user.role, "approver"):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=(
                        f"moving into '{dest.name}' is approval-gated; "
                        "requires role 'approver' or higher"
                    ),
                )
    try:
        result = transition_target(
            session,
            target_id=target_id,
            to_column_id=body.column_id,
            actor_id=user.id,
            justification=body.justification,
            approving_role=body.approving_role,
            publisher_dispatch=_dispatcher,
        )
    except PromotionDenied as exc:
        if "target not found" in str(exc):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    audit = result.event
    target_row = session.get(TargetTable, target_id)
    board_id = target_row.board_id if target_row is not None else None
    get_broker().publish(
        user.workspace_id,
        make_event(
            event_type="target.moved",
            workspace_id=user.workspace_id,
            board_id=board_id,
            target_id=audit.target_id,
            occurred_at=audit.occurred_at.isoformat(),
            data={
                "from_column_id": str(audit.from_column_id) if audit.from_column_id else None,
                "to_column_id": str(audit.to_column_id) if audit.to_column_id else None,
                "justification": audit.justification,
            },
        ),
    )
    return result.target


@router.post("/{target_id}/reorder", response_model=Target)
def reorder_target(
    target_id: UUID,
    body: TargetReorder,
    request: Request,
    session: Session = Depends(db_session),
    user: UserTable = Depends(current_user),
) -> Target:
    """Place a target at a specific spot inside its column.

    Drag-reorder within a column doesn't go through the workflow engine
    (no column transition, no approval gate, no publisher dispatch).
    Just an `order` change. Audit-emitted as 'reordered'. tw-owu.
    """
    require_role(user.role, "operator", action="reorder target")
    target_row = session.get(TargetTable, target_id)
    if target_row is None or target_row.workspace_id != user.workspace_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="target not found")
    enforce_token_scope(request, "targets:write", f"targets:write:board:{target_row.board_id}")
    row = repo.reorder_target(
        session,
        target_id=target_id,
        column_id=body.column_id,
        after_id=body.after_id,
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="target or anchor not found in column",
        )
    updated = repo.get_target(session, target_id)
    assert updated is not None
    record_event(
        session,
        workspace_id=user.workspace_id,
        target_id=target_id,
        actor_id=user.id,
        event_type="reordered",
        justification=f"drag-reorder by {user.email}",
        metadata={
            "column_id": str(body.column_id),
            "after_id": str(body.after_id) if body.after_id else None,
            "position": row.position,
        },
    )
    get_broker().publish(
        user.workspace_id,
        make_event(
            event_type="target.reordered",
            workspace_id=user.workspace_id,
            board_id=row.board_id,
            target_id=target_id,
            occurred_at=row.updated_at.isoformat(),
            data={
                "column_id": str(body.column_id),
                "after_id": str(body.after_id) if body.after_id else None,
                "position": row.position,
            },
        ),
    )
    return updated
