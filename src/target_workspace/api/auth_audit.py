"""Signed auth audit helpers shared by authentication flows."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlmodel import Session, col, select

from target_workspace.db.tables import AuditEventTable, WorkspaceTable


def emit_auth_event(
    session: Session,
    *,
    workspace_id: UUID,
    actor_id: UUID | None,
    event_type: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Append a signed auth audit event. Caller commits."""
    from target_workspace.api.signing import sign_audit_event  # noqa: PLC0415

    row = AuditEventTable(
        workspace_id=workspace_id,
        target_id=None,
        actor_id=actor_id,
        event_type=event_type,
        occurred_at=datetime.now(tz=UTC),
        metadata_json=dict(metadata or {}),
    )
    session.add(row)
    session.flush()
    peer_id, sig, prev_hash = sign_audit_event(
        session,
        event_id=row.id,
        workspace_id=row.workspace_id,
        actor_id=row.actor_id,
        event_type=row.event_type,
        target_id=row.target_id,
        occurred_at=row.occurred_at,
        metadata=row.metadata_json,
    )
    row.peer_id = peer_id
    row.prev_hash = prev_hash
    row.signature = sig
    session.add(row)
    session.flush()

    from target_workspace.api.triggers import (  # noqa: PLC0415
        EmittedAuditEvent,
        fan_out,
    )

    fan_out(
        EmittedAuditEvent(
            id=row.id,
            workspace_id=row.workspace_id,
            event_type=row.event_type,
            actor_id=row.actor_id,
            target_id=row.target_id,
            occurred_at=row.occurred_at,
            metadata=dict(row.metadata_json),
            peer_id=row.peer_id,
            signature=row.signature,
        )
    )


def default_workspace_id(session: Session) -> UUID | None:
    row = session.exec(select(WorkspaceTable).order_by(col(WorkspaceTable.created_at))).first()
    return row.id if row else None


def ua_family(user_agent: str) -> str:
    if not user_agent:
        return "unknown"
    ua_lower = user_agent.lower()
    for needle in (
        "firefox",
        "chrome",
        "safari",
        "edge",
        "opera",
        "curl",
        "wget",
        "python",
        "go-http",
    ):
        if needle in ua_lower:
            return needle
    return user_agent.split("/", 1)[0].lower()


def detect_suspicious(
    session: Session,
    *,
    user_id: UUID,
    client_ip: str,
    ua_family_value: str,
) -> list[str]:
    rows = session.exec(
        select(AuditEventTable)
        .where(AuditEventTable.actor_id == user_id)
        .where(AuditEventTable.event_type == "auth.login.success"),
    ).all()
    if not rows:
        return ["first_login"]
    seen_ips: set[str] = set()
    seen_uas: set[str] = set()
    for row in rows:
        metadata = dict(row.metadata_json or {})
        ip = metadata.get("client_ip")
        ua = metadata.get("ua_family")
        if ip:
            seen_ips.add(str(ip))
        if ua:
            seen_uas.add(str(ua))
    reasons: list[str] = []
    if client_ip and client_ip not in seen_ips:
        reasons.append("new_ip")
    if ua_family_value and ua_family_value not in seen_uas:
        reasons.append("new_user_agent")
    return reasons
