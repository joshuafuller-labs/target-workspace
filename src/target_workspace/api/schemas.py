"""API request/response schemas distinct from the data models.

Many endpoints accept partial / transformed payloads (e.g., TargetCreate
embeds board_id + column_id explicitly). Keeping API schemas separate from
storage models lets the API evolve without breaking persistence and vice
versa.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from target_workspace.utc_datetime import UTCDatetime

LoginIdentifier = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=320),
]


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Wire name remains `email` for compatibility with existing clients,
    # but the value is a login identifier and may be a non-email username.
    email: LoginIdentifier
    password: str = Field(min_length=1)


class UserOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    email: str
    display_name: str
    role: str
    # tw-4exk: SPA reads this to render a force-change-password dialog
    # on first navigation. Backend gates all non-/v1/auth routes when True.
    must_change_password: bool = False
    # tw-mg1a: indicates whether the user has TOTP MFA active.
    mfa_enabled: bool = False
    # tw-tl9r: TAK callsign for PLI binding (null if unset).
    tak_callsign: str | None = None


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(min_length=1)
    new_password: str = Field(min_length=1)


class ColumnIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    order: int = Field(ge=0)
    wip_limit: int | None = Field(default=None, ge=1)
    color: str | None = Field(default=None, max_length=32)
    requires_approval: bool = False
    # tw-cck: dropdown hint for SPA ApprovalPrompt.
    expected_approving_roles: list[str] = Field(default_factory=list)


class BoardCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    columns: list[ColumnIn] = Field(min_length=1)
    transitions: str = Field(default="unrestricted")  # 'unrestricted'|'sequential'
    theme: str = Field(default="neutral")  # see ThemeName in models.board


class BoardUpdate(BaseModel):
    """PATCH payload for /v1/boards/{id}. Only metadata (name / theme /
    transitions) is mutable here — column add/edit/delete on a live
    board has its own bd (tw-itn) because it can affect targets in
    those columns."""

    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=120)
    transitions: str | None = Field(default=None)
    theme: str | None = Field(default=None)


class EllipseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    semi_major_m: float = Field(gt=0.0)
    semi_minor_m: float = Field(gt=0.0)
    bearing_deg: float = Field(ge=0.0, lt=360.0)


class TargetCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    board_id: UUID
    column_id: UUID
    name: str = Field(min_length=1, max_length=200)
    cot_type: str = Field(default="a-u-G", min_length=1)
    category: str | None = None
    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)
    hae: float | None = None
    ce: float | None = Field(default=None, ge=0.0)
    le: float | None = Field(default=None, ge=0.0)
    time: datetime
    stale: datetime | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    remarks: str | None = Field(default=None, max_length=4000)
    source: str | None = Field(default=None, max_length=200)
    geometry_kind: str = Field(default="point")
    geometry_quality: str = Field(default="single-source")
    ellipse: EllipseIn | None = None
    polygon_vertices: list[list[float]] | None = None
    custom_fields: dict[str, Any] = Field(default_factory=dict)


class TargetUpdate(BaseModel):
    """Partial-update payload for `PATCH /v1/targets/{id}`.

    Any field may be edited as new information arrives — an intel analyst
    refining a track, a watch officer correcting attribution, a sensor
    operator tightening a position estimate. Every accepted PATCH bumps
    `version` and fans out as a `target.updated` realtime event.

    Workflow-relevant column transitions are intentionally NOT here — those
    go through `POST /v1/targets/{id}/move` so the audit chain stays
    linear and approval gates aren't bypassed.

    All fields optional; only present keys are applied.
    """

    model_config = ConfigDict(extra="forbid")
    # Identity / classification
    name: str | None = Field(default=None, min_length=1, max_length=200)
    cot_type: str | None = Field(default=None, min_length=1, max_length=120)
    category: str | None = Field(default=None, max_length=120)
    # Geometry (WGS84) — refined as track quality improves
    lat: float | None = Field(default=None, ge=-90.0, le=90.0)
    lon: float | None = Field(default=None, ge=-180.0, le=180.0)
    hae: float | None = None
    ce: float | None = Field(default=None, ge=0.0)
    le: float | None = Field(default=None, ge=0.0)
    # Time — source-observed; correct as needed
    time: datetime | None = None
    stale: datetime | None = None
    # AI / source signal
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    # Human-authored / attribution
    remarks: str | None = Field(default=None, max_length=4000)
    source: str | None = Field(default=None, max_length=200)
    # Geometry — promote a point target to an ellipse / polygon when new
    # information arrives. The repository layer validates the consistency
    # of geometry_kind + ellipse/polygon_vertices on round-trip.
    geometry_kind: str | None = None
    geometry_quality: str | None = None
    ellipse: EllipseIn | None = None
    polygon_vertices: list[list[float]] | None = None
    # Malleability seam — workspace-defined arbitrary fields
    custom_fields: dict[str, Any] | None = None


class TargetMove(BaseModel):
    model_config = ConfigDict(extra="forbid")
    column_id: UUID
    justification: str | None = Field(default=None, max_length=2000)
    approving_role: str | None = Field(
        default=None,
        max_length=80,
        description="Required if the destination column has requires_approval=True.",
    )


class TargetReorder(BaseModel):
    """Place a target at a specific position within a column.

    after_id is the id of the target this one should land after; null
    means top of column. The server computes a new float position as
    the midpoint of the adjacent rows so no other rows need to move.
    """

    model_config = ConfigDict(extra="forbid")
    column_id: UUID
    after_id: UUID | None = Field(
        default=None,
        description="Target id to place this one after; null = top of column.",
    )


class UserCreate(BaseModel):
    """POST /v1/users payload — admin / commander provisions a user.

    role must be one of the six tier names (rbac._TIERS). Server
    refuses 'admin' unless the caller is admin tier themselves
    (privilege-escalation guard).
    """

    model_config = ConfigDict(extra="forbid")
    email: LoginIdentifier
    display_name: str = Field(min_length=1, max_length=200)
    role: str = Field(
        description=("viewer | observer | operator | approver | commander | admin"),
    )
    password: str = Field(min_length=1, max_length=200)
    # tw-6to0: optional expiry. ISO-8601 UTC datetime. Past values are
    # accepted at creation (the user simply can't log in) so admins can
    # pre-provision and have access auto-lapse.
    expires_at: UTCDatetime | None = None


class UserUpdate(BaseModel):
    """PATCH /v1/users/{id} — partial update of display_name + role + expiry."""

    model_config = ConfigDict(extra="forbid")
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    role: str | None = None
    # tw-6to0: explicit-null clears the expiry (no-expiry). Omit the
    # field to leave the current value unchanged.
    expires_at: UTCDatetime | None = None
    # tw-tl9r: TAK callsign. 1-32 chars, alnum + dash. Explicit null
    # clears; omit to leave unchanged.
    tak_callsign: str | None = Field(default=None, max_length=32)


class UserListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    email: str
    display_name: str
    role: str
    enabled: bool
    created_at: UTCDatetime
    # tw-tl9r: surfaced on user listings + PATCH responses.
    tak_callsign: str | None = None


class AuditEventOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    # target_id and actor_id are nullable to accommodate auth.* events
    # (no target; unknown-email login attempts have no actor) — tw-6llq.
    target_id: UUID | None
    actor_id: UUID | None
    actor_kind: str | None = None
    actor_ref: str | None = None
    event_type: str
    occurred_at: UTCDatetime
    from_column_id: UUID | None
    to_column_id: UUID | None
    justification: str | None
    metadata: dict[str, Any]
    # tw-16c0: federation enabler — every event carries the issuing
    # instance's peer_id and an ed25519 signature over the canonical
    # payload. Nullable for historical / pre-migration events.
    peer_id: UUID | None = None
    prev_hash: str | None = None
    signature: str | None = None
    signature_format_version: int = 1


class InstanceIdentityOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    peer_id: UUID
    public_key_pem: str
