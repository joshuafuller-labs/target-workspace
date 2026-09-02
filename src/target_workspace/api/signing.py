"""ed25519 signing of audit events + instance identity bootstrap.

tw-16c0: per-instance keypair, generated on first use, persisted in
instance_identity. Every audit event is signed at insertion so the
audit log is tamper-evident and cross-instance reassembly (post-MVP)
can verify provenance.

Canonical payload format — change requires a migration / breaking
change. Joined with `|` and utf-8 encoded:

  v1:
    ${event_id}|${peer_id}|${prev_hash_or_empty}|${actor_id_or_empty}|
    ${event_type}|${target_id_or_empty}|${occurred_at_iso_utc_with_Z}|
    ${canonical_metadata_json}

  v2 appends typed actor fields before event_type:
    ${event_id}|${peer_id}|${prev_hash_or_empty}|${actor_id_or_empty}|
    ${actor_kind_or_empty}|${actor_ref_or_empty}|...

`canonical_metadata_json` is json.dumps(metadata, sort_keys=True,
separators=(",", ":")) — deterministic across processes.
"""

from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from sqlalchemy import Uuid, bindparam, text
from sqlmodel import Session, col, select

from target_workspace.db.tables import AuditChainHeadTable, AuditEventTable, InstanceIdentityTable

GENESIS_PREV_HASH = "0" * 64
TYPED_ACTOR_SIGNATURE_FORMAT_VERSION = 2


def _canonical_metadata(metadata: dict[str, Any] | None) -> str:
    return json.dumps(metadata or {}, sort_keys=True, separators=(",", ":"))


def _iso(t: datetime | str) -> str:
    """Render an occurred_at value into a canonical UTC ISO string with `Z`."""
    if isinstance(t, str):
        # Trust DB string; normalize to Z suffix
        if t.endswith("+00:00"):
            return t.replace("+00:00", "Z")
        if not t.endswith("Z"):
            return t + "Z"
        return t
    dt = t.astimezone(UTC) if t.tzinfo else t.replace(tzinfo=UTC)
    return dt.isoformat().replace("+00:00", "Z")


def canonical_payload(
    *,
    event_id: UUID | str,
    peer_id: UUID | str,
    prev_hash: str | None,
    actor_id: UUID | str | None,
    event_type: str,
    target_id: UUID | str | None,
    occurred_at_iso: datetime | str,
    metadata: dict[str, Any] | None,
    actor_kind: str | None = None,
    actor_ref: str | None = None,
    signature_format_version: int = 1,
) -> bytes:
    """Build the deterministic bytes-to-sign for an audit event."""
    parts = [
        str(event_id),
        str(peer_id),
        prev_hash or "",
        str(actor_id) if actor_id else "",
    ]
    if signature_format_version >= TYPED_ACTOR_SIGNATURE_FORMAT_VERSION:
        parts.extend([actor_kind or "", actor_ref or ""])
    parts.extend(
        [
            event_type,
            str(target_id) if target_id else "",
            _iso(occurred_at_iso),
            _canonical_metadata(metadata),
        ]
    )
    return "|".join(parts).encode("utf-8")


def audit_event_hash(
    *,
    event_id: UUID | str,
    peer_id: UUID | str,
    prev_hash: str | None,
    actor_id: UUID | str | None,
    event_type: str,
    target_id: UUID | str | None,
    occurred_at_iso: datetime | str,
    metadata: dict[str, Any] | None,
    signature: str,
    actor_kind: str | None = None,
    actor_ref: str | None = None,
    signature_format_version: int = 1,
) -> str:
    payload = canonical_payload(
        event_id=event_id,
        peer_id=peer_id,
        prev_hash=prev_hash,
        actor_id=actor_id,
        actor_kind=actor_kind,
        actor_ref=actor_ref,
        event_type=event_type,
        target_id=target_id,
        occurred_at_iso=occurred_at_iso,
        metadata=metadata,
        signature_format_version=signature_format_version,
    )
    return hashlib.sha256(payload + b"|" + signature.encode("ascii")).hexdigest()


def _latest_event_hash(
    session: Session,
    *,
    workspace_id: UUID,
    peer_id: UUID,
) -> str:
    row = session.exec(
        select(AuditEventTable)
        .where(AuditEventTable.workspace_id == workspace_id)
        .where(AuditEventTable.peer_id == peer_id)
        .order_by(col(AuditEventTable.occurred_at).desc(), col(AuditEventTable.id).desc()),
    ).first()
    if row is None or row.signature is None:
        return GENESIS_PREV_HASH
    return audit_event_hash(
        event_id=row.id,
        peer_id=peer_id,
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


def _ensure_chain_head(
    session: Session,
    *,
    workspace_id: UUID,
    peer_id: UUID,
) -> AuditChainHeadTable:
    bootstrap_hash = _latest_event_hash(
        session,
        workspace_id=workspace_id,
        peer_id=peer_id,
    )
    now = datetime.now(tz=UTC)
    bind = session.get_bind()
    compact_uuid = bind is not None and bind.dialect.name == "sqlite"
    workspace_value = workspace_id.hex if compact_uuid else workspace_id
    peer_value = peer_id.hex if compact_uuid else peer_id
    statement = text(
        """
            INSERT INTO audit_chain_head (workspace_id, peer_id, head_hash, updated_at)
            VALUES (:workspace_id, :peer_id, :head_hash, :updated_at)
            ON CONFLICT (workspace_id, peer_id) DO NOTHING
            """,
    )
    if not compact_uuid:
        statement = statement.bindparams(
            bindparam("workspace_id", type_=Uuid()),
            bindparam("peer_id", type_=Uuid()),
        )
    session.execute(
        statement.bindparams(
            workspace_id=workspace_value,
            peer_id=peer_value,
            head_hash=bootstrap_hash,
            updated_at=now,
        )
    )
    session.flush()
    return session.exec(
        select(AuditChainHeadTable)
        .where(AuditChainHeadTable.workspace_id == workspace_id)
        .where(AuditChainHeadTable.peer_id == peer_id)
        .with_for_update()
    ).one()


def get_or_create_identity(session: Session) -> InstanceIdentityTable:
    """Return this instance's identity, creating it on first call."""
    row = session.exec(select(InstanceIdentityTable)).first()
    if row is not None:
        return row
    private_key = Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    public_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("ascii")
    )
    row = InstanceIdentityTable(
        peer_id=uuid4(),
        public_key_pem=public_pem,
        private_key_pem=private_pem,
        created_at=datetime.now(tz=UTC),
    )
    session.add(row)
    session.flush()
    session.refresh(row)
    return row


def load_private(identity: InstanceIdentityTable) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(
        identity.private_key_pem.encode("ascii"), password=None
    )
    assert isinstance(key, Ed25519PrivateKey)
    return key


def load_public(identity: InstanceIdentityTable) -> Ed25519PublicKey:
    key = serialization.load_pem_public_key(identity.public_key_pem.encode("ascii"))
    assert isinstance(key, Ed25519PublicKey)
    return key


def sign_audit_event(
    session: Session,
    *,
    event_id: UUID,
    actor_id: UUID | None,
    event_type: str,
    target_id: UUID | None,
    occurred_at: datetime,
    metadata: dict[str, Any] | None,
    actor_kind: str | None = None,
    actor_ref: str | None = None,
    workspace_id: UUID | None = None,
    prev_hash: str | None = None,
    signature_format_version: int = 1,
) -> tuple[UUID, str, str | None]:
    """Return (peer_id, base64_signature, prev_hash) for the given event fields.

    Caller is expected to write peer_id + prev_hash + signature onto the audit_event
    row before committing.
    """
    identity = get_or_create_identity(session)
    chain_head: AuditChainHeadTable | None = None
    if prev_hash is None and workspace_id is not None:
        chain_head = _ensure_chain_head(
            session,
            workspace_id=workspace_id,
            peer_id=identity.peer_id,
        )
        prev_hash = chain_head.head_hash
    payload = canonical_payload(
        event_id=event_id,
        peer_id=identity.peer_id,
        prev_hash=prev_hash,
        actor_id=actor_id,
        actor_kind=actor_kind,
        actor_ref=actor_ref,
        event_type=event_type,
        target_id=target_id,
        occurred_at_iso=occurred_at,
        metadata=metadata,
        signature_format_version=signature_format_version,
    )
    private_key = load_private(identity)
    sig = private_key.sign(payload)
    encoded_sig = base64.b64encode(sig).decode("ascii")
    if chain_head is not None:
        chain_head.head_hash = audit_event_hash(
            event_id=event_id,
            peer_id=identity.peer_id,
            prev_hash=prev_hash,
            actor_id=actor_id,
            actor_kind=actor_kind,
            actor_ref=actor_ref,
            event_type=event_type,
            target_id=target_id,
            occurred_at_iso=occurred_at,
            metadata=metadata,
            signature=encoded_sig,
            signature_format_version=signature_format_version,
        )
        chain_head.updated_at = datetime.now(tz=UTC)
        session.add(chain_head)
        session.flush()
    return identity.peer_id, encoded_sig, prev_hash


def backfill_legacy_audit_chain(session: Session) -> int:
    """Sign and hash-chain workspaces that still contain unsigned legacy rows.

    Early dogfood data predates `peer_id`, `signature`, and `prev_hash`. Once
    any such row exists, later signed rows in that workspace must be re-signed
    too so `/v1/audit/verify` can walk one continuous chronological chain.
    """
    legacy_rows = session.exec(
        select(AuditEventTable).where(
            (AuditEventTable.peer_id == None)  # noqa: E711
            | (AuditEventTable.signature == None)  # noqa: E711
        )
    ).all()
    workspace_ids = {row.workspace_id for row in legacy_rows}
    if not workspace_ids:
        return 0

    identity = get_or_create_identity(session)
    private_key = load_private(identity)
    backfilled = 0

    for workspace_id in workspace_ids:
        rows = session.exec(
            select(AuditEventTable)
            .where(AuditEventTable.workspace_id == workspace_id)
            .order_by(col(AuditEventTable.occurred_at).asc(), col(AuditEventTable.id).asc())
        ).all()
        prev_hash = GENESIS_PREV_HASH
        for row in rows:
            payload = canonical_payload(
                event_id=row.id,
                peer_id=identity.peer_id,
                prev_hash=prev_hash,
                actor_id=row.actor_id,
                actor_kind=row.actor_kind,
                actor_ref=row.actor_ref,
                event_type=row.event_type,
                target_id=row.target_id,
                occurred_at_iso=row.occurred_at,
                metadata=row.metadata_json,
                signature_format_version=row.signature_format_version,
            )
            encoded_sig = base64.b64encode(private_key.sign(payload)).decode("ascii")
            row.peer_id = identity.peer_id
            row.prev_hash = prev_hash
            row.signature = encoded_sig
            session.add(row)
            prev_hash = audit_event_hash(
                event_id=row.id,
                peer_id=identity.peer_id,
                prev_hash=row.prev_hash,
                actor_id=row.actor_id,
                actor_kind=row.actor_kind,
                actor_ref=row.actor_ref,
                event_type=row.event_type,
                target_id=row.target_id,
                occurred_at_iso=row.occurred_at,
                metadata=row.metadata_json,
                signature=encoded_sig,
                signature_format_version=row.signature_format_version,
            )
            backfilled += 1

        head = session.get(AuditChainHeadTable, (workspace_id, identity.peer_id))
        if head is None:
            head = AuditChainHeadTable(
                workspace_id=workspace_id,
                peer_id=identity.peer_id,
                head_hash=prev_hash,
                updated_at=datetime.now(tz=UTC),
            )
        else:
            head.head_hash = prev_hash
            head.updated_at = datetime.now(tz=UTC)
        session.add(head)
    session.flush()
    return backfilled
