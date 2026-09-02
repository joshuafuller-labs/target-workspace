"""SQLModel tables — persistence side of the data layer.

Mirror the API schemas in `target_workspace.models`. Repository functions
convert between these tables and the Pydantic models at the boundary.

Two conventions:
- UUID primary keys stored as TEXT in SQLite, UUID in Postgres (sqlalchemy's
  Uuid type handles both).
- dict/list fields persisted as JSON via sqlalchemy's JSON type.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class WorkspaceTable(SQLModel, table=True):
    __tablename__ = "workspace"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    name: str
    created_at: datetime
    # tw-r1ru: role names whose holders must have totp_enabled before
    # they can be granted the role. Empty list = no policy. Persisted
    # as JSON because SQLite has no array type.
    mfa_required_roles: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    # tw-smc: tunable workspace settings (override the env-var defaults).
    brand_name: str | None = None
    default_theme: str = Field(default="neutral")
    freshness_active_seconds: int = Field(default=15)
    freshness_coasting_seconds: int = Field(default=60)
    freshness_stale_seconds: int = Field(default=180)
    correlation_radius_m: float = Field(default=100.0)


class UserTable(SQLModel, table=True):
    __tablename__ = "user"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    workspace_id: UUID = Field(foreign_key="workspace.id", index=True)
    email: str = Field(unique=True, index=True)
    display_name: str
    role: str = Field(default="viewer")
    password_hash: str = Field(description="bcrypt hash; never echoed via the API.")
    created_at: datetime
    # User lifecycle (tw-41on). enabled=False blocks login without
    # destroying audit history; deleted_at marks a soft-delete (the row
    # stays for foreign-key targets in audit_event but is invisible to
    # listing endpoints).
    enabled: bool = Field(default=True)
    deleted_at: datetime | None = None
    # Set True when an admin/commander provisions the user with a temp
    # password; cleared when the user posts /v1/auth/change-password.
    # See migration d4e72ff1a932 (tw-4exk).
    must_change_password: bool = Field(default=False)
    # tw-6to0: time-bound access. When non-null and <= now(), auth layer
    # rejects login and any subsequent request. Useful for ad-hoc strike
    # teams whose access should lapse gracefully when their op ends.
    expires_at: datetime | None = None
    # tw-gmq7: account lockout. Set by the auth layer after N failed
    # logins in a rolling window; cleared by admin unlock.
    locked_until: datetime | None = None
    # tw-ptn2: monotonic version in the signed session cookie. Bumping
    # invalidates every existing cookie for this user (revoke-all).
    # Auto-bumped on password change.
    session_version: int = Field(default=0)
    # tw-mg1a: TOTP MFA. totp_secret is the base32-encoded shared secret;
    # populated on enroll, cleared on disable. totp_enabled flips True
    # after the first successful verify-enroll.
    totp_secret: str | None = None
    totp_enabled: bool = Field(default=False)
    totp_activated_at: datetime | None = None
    # tw-tl9r: TAK callsign for PLI binding. Workspace-scoped unique
    # via composite index (see migration e1ab437c92d5).
    tak_callsign: str | None = None


class BoardTable(SQLModel, table=True):
    __tablename__ = "board"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    workspace_id: UUID = Field(foreign_key="workspace.id", index=True)
    name: str
    transitions: str = Field(default="unrestricted")  # 'unrestricted' | 'sequential'
    theme: str = Field(default="neutral")  # see models.board.ThemeName
    # tw-icj8: optional sub-org ownership. Null = workspace-level board
    # (every workspace member can see it).
    owning_group_id: UUID | None = Field(
        default=None,
        foreign_key="workspace_group.id",
        ondelete="SET NULL",
    )


class ColumnTable(SQLModel, table=True):
    __tablename__ = "column"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    board_id: UUID = Field(foreign_key="board.id", index=True)
    name: str
    order: int
    wip_limit: int | None = None
    color: str | None = None
    requires_approval: bool = Field(default=False)
    # tw-cck: dropdown hint for ApprovalPrompt — list of role strings
    # that satisfy this column's approval gate. Free-text fallback when
    # empty. Backend doesn't enforce the list contents.
    expected_approving_roles: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON),
    )


class PromotionPolicyTable(SQLModel, table=True):
    __tablename__ = "promotion_policy"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    workspace_id: UUID = Field(foreign_key="workspace.id", index=True)
    mode: str
    min_confidence: float | None = None
    # UUIDs stored as strings in JSON columns (SQLAlchemy's JSON encoder
    # rejects raw UUID instances).
    required_stages: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    approval_roles: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    auto_publish_column_id: UUID | None = Field(
        default=None,
        foreign_key="column.id",
        ondelete="SET NULL",
    )
    on_low_confidence_route_to_column_id: UUID | None = Field(
        default=None,
        foreign_key="column.id",
        ondelete="SET NULL",
    )


class SourceConfigTable(SQLModel, table=True):
    __tablename__ = "source_config"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    workspace_id: UUID = Field(foreign_key="workspace.id", index=True)
    name: str
    plugin_type: str
    enabled: bool = Field(default=True)
    adapter_config: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    normalization_map: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    promotion_policy_id: UUID | None = Field(
        default=None,
        foreign_key="promotion_policy.id",
        ondelete="SET NULL",
    )


class PublisherConfigTable(SQLModel, table=True):
    __tablename__ = "publisher_config"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    workspace_id: UUID = Field(foreign_key="workspace.id", index=True)
    name: str
    plugin_type: str
    enabled: bool = Field(default=True)
    adapter_config: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    # UUIDs stored as strings; converted at the engine boundary.
    column_filter_ids: list[str] = Field(default_factory=list, sa_column=Column(JSON))


class TargetTable(SQLModel, table=True):
    __tablename__ = "target"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    workspace_id: UUID = Field(foreign_key="workspace.id", index=True)
    board_id: UUID = Field(foreign_key="board.id", index=True)
    column_id: UUID = Field(foreign_key="column.id", index=True)

    name: str
    cot_type: str = Field(default="a-u-G")
    category: str | None = None

    lat: float
    lon: float
    hae: float | None = None
    ce: float | None = None
    le: float | None = None

    time: datetime
    stale: datetime | None = None

    confidence: float | None = None
    version: int = Field(default=1)
    # Human-authored fields surfaced on CoT publish
    remarks: str | None = None
    source: str | None = None
    # Geometry — point/ellipse/polygon. lat/lon above is the anchor.
    geometry_kind: str = Field(default="point")
    ellipse: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    polygon_vertices: list[list[float]] | None = Field(default=None, sa_column=Column(JSON))
    geometry_quality: str = Field(default="single-source")
    custom_fields: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    # tw-5kqh: callsigns assigned to this target (free-form strings).
    # User-callsign mapping (tw-tl9r) will validate later.
    assigned_callsigns: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    created_at: datetime
    updated_at: datetime
    observation_count: int = Field(default=1)
    # Float ordinal for within-column ordering. Drag-reorder inserts a
    # new value as the midpoint between adjacent rows so we never have
    # to renumber the column. Default 0 keeps inserted rows on top until
    # explicitly placed. tw-owu.
    position: float = Field(default=0.0, index=True)


class TrackObservationTable(SQLModel, table=True):
    """Per-observation row for a Target — the append-only sensor-hit log.

    Per docs/research/ukraine-fires-targeting.md §1: Delta handles 600K+
    submissions/month. The same physical contact observed N times is one
    target, not N. Every POST /v1/targets that matches an existing track
    appends a row here instead of creating a new Target.
    """

    __tablename__ = "track_observation"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    workspace_id: UUID = Field(foreign_key="workspace.id", index=True)
    target_id: UUID = Field(foreign_key="target.id", index=True)
    observed_at: datetime = Field(index=True)
    lat: float
    lon: float
    hae: float | None = None
    ce: float | None = None
    confidence: float | None = None
    source: str | None = None
    classification: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))
    created_at: datetime


class AuditEventTable(SQLModel, table=True):
    __tablename__ = "audit_event"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    workspace_id: UUID = Field(foreign_key="workspace.id", index=True)
    # target_id and actor_id are nullable to accommodate auth.* events
    # which may have no target and (for unknown-email login attempts) no
    # actor. See migration c7a91e22b801 (tw-6llq).
    target_id: UUID | None = Field(default=None, foreign_key="target.id", index=True)
    actor_id: UUID | None = Field(default=None, foreign_key="user.id", index=True)
    actor_kind: str | None = Field(default="human_user", index=True)
    actor_ref: str | None = Field(default=None, index=True)
    event_type: str
    occurred_at: datetime = Field(index=True)
    from_column_id: UUID | None = Field(default=None, foreign_key="column.id", ondelete="SET NULL")
    to_column_id: UUID | None = Field(default=None, foreign_key="column.id", ondelete="SET NULL")
    justification: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column("metadata", JSON))
    # tw-16c0: federation enabler slots. peer_id is the issuing instance
    # (always the local instance for now; cross-instance ingest is post-MVP).
    # signature is base64(ed25519(canonical_payload)). Both nullable for
    # backfill / forward-compatibility — populated on insert by the app.
    peer_id: UUID | None = Field(default=None, index=True)
    prev_hash: str | None = Field(default=None, index=True)
    signature: str | None = None
    signature_format_version: int = Field(default=1)


class AuditChainHeadTable(SQLModel, table=True):
    __tablename__ = "audit_chain_head"

    workspace_id: UUID = Field(foreign_key="workspace.id", primary_key=True)
    peer_id: UUID = Field(primary_key=True, index=True)
    head_hash: str
    updated_at: datetime


class WorkflowNominationTable(SQLModel, table=True):
    __tablename__ = "workflow_nomination"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    workspace_id: UUID = Field(foreign_key="workspace.id", index=True)
    target_id: UUID = Field(foreign_key="target.id", index=True)
    from_column_id: UUID = Field(foreign_key="column.id")
    to_column_id: UUID = Field(foreign_key="column.id", index=True)
    proposed_by: str = Field(index=True)
    actor_id: UUID = Field(foreign_key="user.id", index=True)
    approver_role: str
    reason: str
    evidence_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column("evidence", JSON))
    status: str = Field(default="pending", index=True)
    created_at: datetime
    resolved_at: datetime | None = None
    resolved_by: UUID | None = Field(default=None, foreign_key="user.id", ondelete="SET NULL")


class PositionTable(SQLModel, table=True):
    """ICS position — IC / OSC / PSC / LSC / FSC / SAFETY / PIO / LIAISON
    (tw-l40z). Seeded per workspace on bootstrap."""

    __tablename__ = "position"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    workspace_id: UUID = Field(foreign_key="workspace.id", index=True, ondelete="CASCADE")
    name: str
    ics_code: str  # 'IC', 'OSC', etc.
    description: str | None = None
    created_at: datetime


class PositionAssignmentTable(SQLModel, table=True):
    """Time-windowed assignment of a user to a position. tw-l40z."""

    __tablename__ = "position_assignment"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    position_id: UUID = Field(foreign_key="position.id", index=True, ondelete="CASCADE")
    user_id: UUID = Field(foreign_key="user.id", index=True)
    op_period_id: UUID | None = Field(
        default=None,
        foreign_key="op_period.id",
        ondelete="SET NULL",
    )
    started_at: datetime
    ends_at: datetime | None = None
    transferred_from_assignment_id: UUID | None = Field(
        default=None,
        foreign_key="position_assignment.id",
        ondelete="SET NULL",
    )
    transferred_by_user_id: UUID | None = Field(
        default=None,
        foreign_key="user.id",
        ondelete="SET NULL",
    )
    notes: str | None = None


class OpPeriodTable(SQLModel, table=True):
    """ICS operational period (tw-eebq).

    One active period per board at a time; opening a new one auto-closes
    the previous active period.
    """

    __tablename__ = "op_period"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    board_id: UUID = Field(foreign_key="board.id", index=True)
    number: int  # 1, 2, 3 ... per-board
    started_at: datetime
    ends_at: datetime | None = None
    started_by_user_id: UUID = Field(foreign_key="user.id")
    closed_by_user_id: UUID | None = Field(default=None, foreign_key="user.id", ondelete="SET NULL")
    status: str = Field(default="active")  # 'active' | 'closed'
    iap: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON))


class TargetBoardLinkTable(SQLModel, table=True):
    """Cross-board target link per ADR 0017 (tw-v8s).

    A target appears on a board iff a non-tombstoned row exists here.
    column_id + position are PER-BOARD. The originating board+column
    still live on TargetTable for back-compat; that record is the
    'home' link conceptually but is not privileged.
    """

    __tablename__ = "target_board_link"

    target_id: UUID = Field(
        foreign_key="target.id",
        primary_key=True,
        index=True,
        ondelete="CASCADE",
    )
    board_id: UUID = Field(foreign_key="board.id", primary_key=True, index=True, ondelete="CASCADE")
    column_id: UUID = Field(foreign_key="column.id")
    position: int = Field(default=0)
    added_at: datetime
    added_by: UUID | None = Field(default=None, foreign_key="user.id", ondelete="SET NULL")
    removed_at: datetime | None = None
    status: str = Field(default="active")  # 'active' | 'removed' | 'transferred'


class BoardAclTable(SQLModel, table=True):
    """Per-board role overlay. tw-liwf.

    Resolution: workspace tier → group_membership → board_acl → target_acl.
    """

    __tablename__ = "board_acl"

    board_id: UUID = Field(foreign_key="board.id", primary_key=True, index=True, ondelete="CASCADE")
    user_id: UUID = Field(foreign_key="user.id", primary_key=True, index=True, ondelete="CASCADE")
    role_overlay: str


class TargetAclTable(SQLModel, table=True):
    """Per-target permission grant. tw-liwf.

    perms is a comma-separated permission list ('read', 'write',
    'approve', 'delete'). Future v1.1: structured enum + bitmap.
    """

    __tablename__ = "target_acl"

    target_id: UUID = Field(
        foreign_key="target.id",
        primary_key=True,
        index=True,
        ondelete="CASCADE",
    )
    user_id: UUID = Field(foreign_key="user.id", primary_key=True, index=True, ondelete="CASCADE")
    perms: str


class ResourceTable(SQLModel, table=True):
    """ICS-211 resource entry (tw-qkp).

    A resource is a person + their certifications, checked in to the
    incident. Tracked by callsign; not the same model as user (a user
    is the workspace identity; a resource is a deployed asset).
    """

    __tablename__ = "resource"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    workspace_id: UUID = Field(foreign_key="workspace.id", index=True, ondelete="CASCADE")
    callsign: str
    name: str
    certifications: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    location: str | None = None
    status: str = Field(default="checked-in")  # 'checked-in' | 'checked-out'
    checked_in_at: datetime
    checked_out_at: datetime | None = None


class WorkspaceGroupTable(SQLModel, table=True):
    """Sub-org abstraction per ADR 0015 / tw-icj8."""

    __tablename__ = "workspace_group"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    workspace_id: UUID = Field(foreign_key="workspace.id", index=True, ondelete="CASCADE")
    name: str
    description: str | None = None
    expires_at: datetime | None = None
    created_at: datetime
    deleted_at: datetime | None = None


class WorkspaceGroupMemberTable(SQLModel, table=True):
    """Composite-PK membership for a workspace group. tw-icj8."""

    __tablename__ = "workspace_group_member"

    group_id: UUID = Field(
        foreign_key="workspace_group.id",
        primary_key=True,
        index=True,
        ondelete="CASCADE",
    )
    user_id: UUID = Field(foreign_key="user.id", primary_key=True, index=True, ondelete="CASCADE")
    role_in_group: str | None = None
    joined_at: datetime
    expires_at: datetime | None = None


class ApiTokenTable(SQLModel, table=True):
    """Long-lived bearer token for service-account auth (tw-sodu)."""

    __tablename__ = "api_token"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    workspace_id: UUID = Field(foreign_key="workspace.id", index=True, ondelete="CASCADE")
    created_by_user_id: UUID = Field(foreign_key="user.id")
    name: str
    token_hash: str = Field(unique=True)
    preview: str  # first 8 chars of plaintext, displayed in listings
    role: str  # snapshot of creator's role at issue time
    scopes: list[str] | None = Field(default=None, sa_column=Column(JSON))
    expires_at: datetime | None = None
    created_at: datetime
    revoked_at: datetime | None = None
    last_used_at: datetime | None = None


class PasswordResetTokenTable(SQLModel, table=True):
    """Single-use, short-TTL password reset token. tw-qj9k.

    token_hash is sha256(plaintext) — plaintext only lives inside the
    outgoing email body. used_at marks redemption; second redemption
    returns 409.
    """

    __tablename__ = "password_reset_token"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True, ondelete="CASCADE")
    token_hash: str = Field(unique=True)
    expires_at: datetime
    created_at: datetime
    used_at: datetime | None = None


class PasskeyCredentialTable(SQLModel, table=True):
    """WebAuthn credential registered to a user."""

    __tablename__ = "passkey_credential"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="user.id", index=True, ondelete="CASCADE")
    name: str
    credential_id: str = Field(unique=True, index=True)
    public_key: str
    sign_count: int = Field(default=0)
    aaguid: str | None = None
    created_at: datetime
    last_used_at: datetime | None = None


class PasskeyChallengeTable(SQLModel, table=True):
    """One-time WebAuthn challenge state."""

    __tablename__ = "passkey_challenge"

    challenge: str = Field(primary_key=True)
    user_id: UUID | None = Field(
        default=None,
        foreign_key="user.id",
        index=True,
        ondelete="CASCADE",
    )
    ceremony: str
    name: str | None = None
    expires_at: datetime
    created_at: datetime


class InvitationTokenTable(SQLModel, table=True):
    """Coordinator-mintable join token. tw-qmnh.

    token_hash is sha256(plaintext) — the plaintext is shown to the
    issuer ONCE on creation and never stored. group_id is reserved for
    when tw-icj8 ships the groups schema.
    """

    __tablename__ = "invitation_token"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    workspace_id: UUID = Field(foreign_key="workspace.id", index=True, ondelete="CASCADE")
    issued_by_user_id: UUID = Field(foreign_key="user.id")
    group_id: UUID | None = Field(
        default=None,
        foreign_key="workspace_group.id",
        ondelete="SET NULL",
    )
    token_hash: str = Field(unique=True)
    role: str
    expires_at: datetime
    max_uses: int = Field(default=1)
    uses_remaining: int = Field(default=1)
    created_at: datetime
    revoked_at: datetime | None = None
    last_used_at: datetime | None = None


class InstanceIdentityTable(SQLModel, table=True):
    """One ed25519 keypair per instance. Bootstrapped on first request.

    tw-16c0: the schema and per-instance keypair ship in MVP so cross-
    instance audit reassembly is cheap to retrofit when federation lands
    (tw-a3ix). Encryption-at-rest for private_key_pem is a v1.1 polish.
    """

    __tablename__ = "instance_identity"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    peer_id: UUID = Field(unique=True)
    public_key_pem: str
    private_key_pem: str
    created_at: datetime


class WorkflowTriggerTable(SQLModel, table=True):
    """Per-board geofence → column-move rules (tw-5m91)."""

    __tablename__ = "workflow_trigger"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    board_id: UUID = Field(foreign_key="board.id", index=True)
    trigger: str
    condition: str
    action_move_to_column_id: UUID = Field(foreign_key="column.id", ondelete="CASCADE")
    justification_template: str
