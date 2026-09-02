"""Track-correlation helpers — distance + time matching of new
observations against existing targets.

Goal (per docs/research/ukraine-fires-targeting.md §1): when a sensor
re-observes a contact you've already seen, don't spawn a new Target —
append the observation to the existing track. Real-world targeting
systems (Delta, GIS Arta) ingest hundreds of thousands of cues per
month; if every cue creates a row, the kanban drowns in dupes.

The MVP correlator matches on:
  - geographic distance within `tol_meters` (default 500 m for points)
  - observation within `tol_seconds` (default 30 minutes)
  - same affiliation prefix in cot_type (a-h-* matches a-h-*, not a-u-*)

Caller does NOT need to know about correlation — the API router calls
`maybe_merge_observation` first; if it returns a target, the new POST
piggy-backs onto it instead of inserting a fresh row.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlmodel import Session, select

from target_workspace.db.tables import TargetTable, TrackObservationTable
from target_workspace.models.target import Target

# Defaults tuned for the bundled scenarios. Adjustable via workspace
# config later (tw-?? when we add per-workspace correlation policy).
DEFAULT_TOL_METERS = 500.0
DEFAULT_TOL_SECONDS = 30 * 60
GEOMETRY_DERIVATION_KEY = "geometry_quality_derivation"
GEOMETRY_OVERRIDE_KEY = "geometry_quality_override"
CORROBORATED_SOURCE_COUNT = 2


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two WGS84 points, meters."""
    radius_earth_m = 6_371_000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius_earth_m * math.asin(math.sqrt(a))


def affiliation_of(cot_type: str) -> str:
    """Extract the MIL-STD-2525 affiliation letter (h/s/u/f/n)."""
    parts = cot_type.split("-")
    return parts[1] if len(parts) > 1 else "u"


def find_matching_track(
    session: Session,
    *,
    workspace_id: UUID,
    board_id: UUID,
    candidate: Target,
    tol_meters: float = DEFAULT_TOL_METERS,
    tol_seconds: float = DEFAULT_TOL_SECONDS,
) -> TargetTable | None:
    """Return the most recently-observed target that matches the
    candidate within distance + time + affiliation tolerances; None if
    no match is close enough.

    Scoped to a single board — different boards represent different
    operational pictures (a county SAR mission ≠ a federal LE case
    board), so a same-coordinate observation submitted to a different
    board must NOT dedupe. Only point targets correlate in v0; ellipses
    and polygons have richer spatial semantics that deserve their own
    matcher.
    """
    if candidate.geometry_kind != "point":
        return None
    now = datetime.now(tz=UTC)
    horizon = now - timedelta(seconds=tol_seconds)
    candidate_aff = affiliation_of(candidate.cot_type)

    rows = session.exec(
        select(TargetTable)
        .where(TargetTable.workspace_id == workspace_id)
        .where(TargetTable.board_id == board_id),
    ).all()
    best: TargetTable | None = None
    best_distance = tol_meters
    for row in rows:
        if row.geometry_kind != "point":
            continue
        if affiliation_of(row.cot_type) != candidate_aff:
            continue
        # `time` is source-observed and may be older than the horizon
        # by minutes; compare to the more permissive of time and
        # updated_at.
        observed = max(_ensure_aware(row.time), _ensure_aware(row.updated_at))
        if observed < horizon:
            continue
        distance = haversine_m(candidate.lat, candidate.lon, row.lat, row.lon)
        if distance < best_distance:
            best_distance = distance
            best = row
    return best


def append_observation(
    session: Session,
    *,
    workspace_id: UUID,
    target_row: TargetTable,
    candidate: Target,
    classification: dict[str, Any] | None = None,
) -> TargetTable:
    """Record the candidate as a new TrackObservation on `target_row`,
    fold its fresher fields into the persistent target, and return the
    updated row. Caller is responsible for `session.flush()`."""
    now = datetime.now(tz=UTC)
    session.add(
        TrackObservationTable(
            id=uuid4(),
            workspace_id=workspace_id,
            target_id=target_row.id,
            observed_at=_ensure_aware(candidate.time),
            lat=candidate.lat,
            lon=candidate.lon,
            hae=candidate.hae,
            ce=candidate.ce,
            confidence=candidate.confidence,
            source=candidate.source,
            classification=classification,
            created_at=now,
        ),
    )
    # Adopt the fresher observation's anchor + version bump. Don't
    # overwrite the operator-authored name / remarks / cot_type — those
    # are intentional state, not sensor outputs.
    target_row.lat = candidate.lat
    target_row.lon = candidate.lon
    if candidate.hae is not None:
        target_row.hae = candidate.hae
    if candidate.ce is not None:
        target_row.ce = candidate.ce
    # tw-a9a/tw-k4kg.10: fuse confidences across independent observations
    # from the immutable observation log, not mutable custom_fields.
    if candidate.confidence is not None or candidate.source is not None:
        from target_workspace.api.confidence_fusion import fuse  # noqa: PLC0415

        chain = confidence_chain_projection(session, target_id=target_row.id)
        fused = fuse([entry["confidence"] for entry in chain])
        if fused is not None:
            target_row.confidence = fused
    _derive_point_geometry_quality(session, target_row=target_row, candidate=candidate)
    target_row.time = _ensure_aware(candidate.time)
    target_row.observation_count += 1
    target_row.version += 1
    target_row.updated_at = now
    session.add(target_row)
    return target_row


def apply_initial_geometry_quality_derivation(target: Target) -> None:
    """Seed visible derivation metadata for a freshly-created target."""
    custom_fields = dict(target.custom_fields or {})
    if target.geometry_kind != "point":
        custom_fields[GEOMETRY_DERIVATION_KEY] = {
            "method": "non_point_fail_closed",
            "derived": target.geometry_quality,
        }
    else:
        target.geometry_quality = "single-source"
        custom_fields[GEOMETRY_DERIVATION_KEY] = {
            "method": "independent_observation_sources",
            "source_count": 1,
            "derived": target.geometry_quality,
        }
    target.custom_fields = custom_fields


def _derive_point_geometry_quality(
    session: Session,
    *,
    target_row: TargetTable,
    candidate: Target,
) -> None:
    if target_row.geometry_kind != "point" or candidate.geometry_kind != "point":
        return
    sources = _independent_observation_sources(session, target_row=target_row, candidate=candidate)
    source_count = len(sources)
    derived = "corroborated" if source_count >= CORROBORATED_SOURCE_COUNT else "single-source"
    custom_fields = dict(target_row.custom_fields or {})
    custom_fields[GEOMETRY_DERIVATION_KEY] = {
        "method": "independent_observation_sources",
        "source_count": source_count,
        "derived": derived,
    }
    override = custom_fields.get(GEOMETRY_OVERRIDE_KEY)
    if isinstance(override, dict) and override.get("value"):
        override["derived"] = derived
        custom_fields[GEOMETRY_OVERRIDE_KEY] = override
        target_row.geometry_quality = str(override["value"])
    else:
        target_row.geometry_quality = derived
    target_row.custom_fields = custom_fields


def _independent_observation_sources(
    session: Session,
    *,
    target_row: TargetTable,
    candidate: Target,
) -> set[str]:
    sources: set[str] = set()
    if target_row.source:
        sources.add(target_row.source)
    rows = session.exec(
        select(TrackObservationTable).where(TrackObservationTable.target_id == target_row.id),
    ).all()
    for row in rows:
        if row.source:
            sources.add(row.source)
    if candidate.source:
        sources.add(candidate.source)
    if not sources:
        sources.add("unknown")
    return sources


def confidence_chain_projection(
    session: Session,
    *,
    target_id: UUID,
    include_candidate: Target | None = None,
) -> list[dict[str, Any]]:
    rows = session.exec(
        select(TrackObservationTable)
        .where(TrackObservationTable.target_id == target_id)
        .order_by(TrackObservationTable.observed_at),  # type: ignore[arg-type]
    ).all()
    chain = [
        {
            "source": row.source or "unknown",
            "confidence": row.confidence,
        }
        for row in rows
        if row.confidence is not None or row.source is not None
    ]
    if include_candidate is not None and (
        include_candidate.confidence is not None or include_candidate.source is not None
    ):
        chain.append(
            {
                "source": include_candidate.source or "unknown",
                "confidence": include_candidate.confidence,
            },
        )
    return chain


def confidence_chain_projection_many(
    session: Session,
    *,
    target_ids: list[UUID],
) -> dict[UUID, list[dict[str, Any]]]:
    if not target_ids:
        return {}
    rows = session.exec(
        select(TrackObservationTable)
        .where(TrackObservationTable.target_id.in_(target_ids))  # type: ignore[attr-defined]
        .order_by(TrackObservationTable.target_id, TrackObservationTable.observed_at),  # type: ignore[arg-type]
    ).all()
    chains: dict[UUID, list[dict[str, Any]]] = {target_id: [] for target_id in target_ids}
    for row in rows:
        if row.confidence is None and row.source is None:
            continue
        chains.setdefault(row.target_id, []).append(
            {
                "source": row.source or "unknown",
                "confidence": row.confidence,
            },
        )
    return chains


def _ensure_aware(dt: datetime) -> datetime:
    """SQLite drops tzinfo on persistence; restore UTC for comparisons."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
