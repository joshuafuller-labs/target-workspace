"""Target — the core entity that moves through the workspace lifecycle.

Per ADR 0008 (malleability) this is the neutral data shape. Workspace-specific
terminology (column names, classification schemes, source types, themes) is
configurable data elsewhere, not baked into this model.

Per ADR 0010 (demo capability) the `time` field is **source-provided** — it
represents when the source detected the event, never when the server received
it. Server-receive is captured separately in audit events.

Per ADR 0012 (mobile MVP) the `version` field is monotonic per Target and
supports offline-first / sync-when-connected semantics.

Per ADR 0013 (API client-agnostic) the model uses `extra="forbid"` so the
OpenAPI spec emits `additionalProperties: false`, producing strict types in
generated clients.
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from target_workspace.utc_datetime import UTCDatetime

# A target isn't always a point. EW direction-finding produces an ellipse
# (the DF cone or an uncertainty footprint); area-effect contacts produce
# polygons. The lat/lon on the Target acts as the geometry's anchor:
# - point   → the location itself
# - ellipse → center of the ellipse; major/minor/bearing carried on `ellipse`
# - polygon → anchor (typically centroid); vertices on `polygon_vertices`
GeometryKind = Literal["point", "ellipse", "polygon"]


# How confident we are in the geometry — per the Ukraine audit (§5), an
# ellipse from a single RF DF collector is operationally a very different
# beast from an ellipse from tri-sensor fusion. RoE matrices key off this
# explicitly: kinetic effectors typically require >= "corroborated".
#
#   bearing-only   : direction known, position is anywhere along the LOB
#   single-source  : one sensor placed the contact; no corroboration
#   corroborated   : >= 2 independent sensors agree
#   confirmed      : ID + position + classification all locked
#
# Ordering is meaningful — workflow gates use it as a "minimum quality"
# precondition. Stored as the literal string in the DB for human-
# readable audits.
GeometryQuality = Literal[
    "bearing-only",
    "single-source",
    "corroborated",
    "confirmed",
]

GEOMETRY_QUALITY_ORDER: dict[str, int] = {
    "bearing-only": 0,
    "single-source": 1,
    "corroborated": 2,
    "confirmed": 3,
}


class Ellipse(BaseModel):
    """Uncertainty / DF ellipse centered on the Target's lat/lon."""

    model_config = ConfigDict(extra="forbid")

    semi_major_m: float = Field(
        gt=0.0,
        description="Semi-major axis in meters (half the long-axis length).",
    )
    semi_minor_m: float = Field(
        gt=0.0,
        description="Semi-minor axis in meters (half the short-axis length).",
    )
    bearing_deg: float = Field(
        ge=0.0,
        lt=360.0,
        description=(
            "Compass bearing of the major axis (true north, degrees clockwise). "
            "For an EW DF cone, this is the line-of-bearing from the collector."
        ),
    )

    @model_validator(mode="after")
    def _major_at_least_minor(self) -> Ellipse:
        if self.semi_minor_m > self.semi_major_m:
            msg = "semi_minor_m must be <= semi_major_m"
            raise ValueError(msg)
        return self


class Target(BaseModel):
    """A target moving through the workspace lifecycle."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
    )

    # Identity
    id: UUID = Field(
        default_factory=uuid4,
        description="Server-issued identifier; stable across the Target's lifecycle.",
    )
    name: str = Field(
        min_length=1,
        max_length=200,
        description="Operator-facing callsign or label.",
    )
    cot_type: str = Field(
        default="a-u-G",
        min_length=1,
        description=(
            "CoT type code (MIL-STD-2525-aligned). Defaults to 'unknown ground' so the "
            "core stays neutral; workspaces override per their taxonomy."
        ),
    )
    category: str | None = Field(
        default=None,
        description="Optional workspace-defined category tag.",
    )

    # Geometry (WGS84)
    lat: float = Field(ge=-90.0, le=90.0, description="Latitude in degrees, WGS84.")
    lon: float = Field(ge=-180.0, le=180.0, description="Longitude in degrees, WGS84.")
    hae: float | None = Field(
        default=None,
        description="Height above ellipsoid (meters), if known.",
    )
    ce: float | None = Field(
        default=None,
        ge=0.0,
        description="Circular error (meters, 1-sigma), if known.",
    )
    le: float | None = Field(
        default=None,
        ge=0.0,
        description="Linear error (meters, 1-sigma), if known.",
    )

    # Time — source-provided per ADR 0010. UTCDatetime ensures the JSON
    # response carries an explicit Z suffix so non-UTC browsers parse it
    # correctly (tw-qt6).
    time: UTCDatetime = Field(
        description=(
            "When the source observed this event. Source-provided; never set from "
            "server-receive (see ADR 0010)."
        ),
    )
    stale: UTCDatetime | None = Field(
        default=None,
        description="When this Target stops being authoritative, if known.",
    )

    # AI / source signal
    confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="0..1; semantics vary by source. None when the source emits no score.",
    )

    # Sync semantics per ADR 0012
    version: int = Field(
        default=1,
        ge=1,
        description="Monotonic per-Target version supporting offline-first sync.",
    )

    # Human-authored fields — editable post-creation, surface on CoT publish
    remarks: str | None = Field(
        default=None,
        max_length=4000,
        description=(
            "Free-text operator note about this target. Maps to the CoT "
            "<remarks> element on publish, with an appended deep-link back "
            "to this card in the SPA for round-tripping from ATAK."
        ),
    )
    source: str | None = Field(
        default=None,
        max_length=200,
        description=(
            "System-of-origin / attribution string. Examples: 'CV-ATR (MQ-9)', "
            "'HUMINT (HCT-7)', 'Ku-band radar DD-3', 'manual entry'. Promoted "
            "from custom_fields.source so it's queryable + round-trips on CoT "
            "publish as <__source system='...'/>."
        ),
    )

    # Geometry primitive — defaults to point so existing data is unchanged.
    # `lat`/`lon`/`hae` above are the anchor; ellipse + polygon_vertices
    # carry the shape-specific parameters.
    geometry_kind: GeometryKind = Field(
        default="point",
        description=(
            "Shape primitive. 'point' uses lat/lon directly; 'ellipse' attaches "
            "an Ellipse object centered on lat/lon; 'polygon' attaches an "
            "ordered list of [lat, lon] vertices."
        ),
    )
    ellipse: Ellipse | None = Field(
        default=None,
        description="Only set when geometry_kind == 'ellipse'.",
    )
    polygon_vertices: list[list[float]] | None = Field(
        default=None,
        description=(
            "Ordered [lat, lon] vertices when geometry_kind == 'polygon'. "
            "Need not be explicitly closed; the renderer closes automatically."
        ),
    )
    geometry_quality: GeometryQuality = Field(
        default="single-source",
        description=(
            "Confidence in the geometry. Approval-gated columns may refuse "
            "kinetic-effector dispatch when this is below 'corroborated' "
            "(RoE practice — see docs/research/ukraine-fires-targeting.md §5)."
        ),
    )

    @model_validator(mode="after")
    def _geometry_consistent(self) -> Target:
        if self.geometry_kind == "ellipse" and self.ellipse is None:
            msg = "geometry_kind='ellipse' requires an `ellipse` object"
            raise ValueError(msg)
        if self.geometry_kind == "polygon":
            min_vertices = 3
            if not self.polygon_vertices or len(self.polygon_vertices) < min_vertices:
                msg = "geometry_kind='polygon' requires polygon_vertices with >= 3 [lat, lon] pairs"
                raise ValueError(msg)
            for v in self.polygon_vertices:
                lat_lon_pair_size = 2
                if len(v) != lat_lon_pair_size:
                    msg = "polygon_vertices entries must be [lat, lon] pairs"
                    raise ValueError(msg)
        return self

    # Malleability seam per ADR 0008
    custom_fields: dict[str, Any] = Field(
        default_factory=dict,
        description="Workspace-defined schema fields; arbitrary JSON-compatible values.",
    )
    # tw-5kqh: callsigns assigned to this target (free-form strings).
    assigned_callsigns: list[str] = Field(
        default_factory=list,
        description="Callsigns currently assigned to act on this target.",
    )
