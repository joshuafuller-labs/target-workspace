"""Signed audit events with peer-id slot (tw-16c0).

Federation enabler. MVP scope is schema slots + LOCAL signing — the
cross-instance ingest piece is post-MVP and gated by tw-a3ix.

Assumption documented in tw-16c0:
  - One ed25519 keypair per instance, persisted in instance_identity
    table. Private key stored AS-IS in the DB at MVP (encryption at
    rest with INSTANCE_KEY env var is filed as a v1.1 polish — see
    tw-16c0 notes). Risk accepted because the DB volume is already
    the trust boundary today.
  - Signature canonicalization: utf-8 concat of
    `${event_id}|${peer_id}|${prev_hash or ""}|${actor_id or ""}|${event_type}|${target_id or ""}|${occurred_at_iso}|${metadata_canonical_json}`
    Deterministic across runs of the same data.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import (
    load_pem_public_key,
)
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.fast]


def _login(c: TestClient) -> None:
    r = c.post("/v1/auth/login", json={"email": "admin@example.com", "password": "test-pw"})
    assert r.status_code == 200, r.text


def test_instance_identity_endpoint_returns_pem_public_key_and_peer_id(
    client: TestClient,
) -> None:
    r = client.get("/v1/instance/identity")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "peer_id" in body
    assert "public_key_pem" in body
    # Loadable PEM ed25519 public key
    load_pem_public_key(body["public_key_pem"].encode())


def test_audit_events_carry_peer_id_and_signature(client: TestClient) -> None:
    _login(client)
    # Login produced an auth.* audit event (tw-6llq)
    r = client.get("/v1/audit?limit=10")
    assert r.status_code == 200, r.text
    events = r.json()
    assert len(events) >= 1
    for e in events:
        assert e.get("peer_id") is not None, f"peer_id missing on {e}"
        assert e.get("signature") is not None, f"signature missing on {e}"


def test_new_audit_events_are_hash_linked_and_verifiable(client: TestClient) -> None:
    _login(client)
    _login(client)

    events = list(reversed(client.get("/v1/audit?limit=10").json()))
    assert len(events) >= 2
    same_peer = [event for event in events if event["peer_id"] == events[-1]["peer_id"]]
    assert len(same_peer) >= 2
    assert same_peer[0]["prev_hash"] is not None
    assert same_peer[1]["prev_hash"] is not None
    assert same_peer[1]["prev_hash"] != same_peer[0]["prev_hash"]

    verify = client.get("/v1/audit/verify")
    assert verify.status_code == 200, verify.text
    body = verify.json()
    assert body["ok"] is True
    assert body["checked"] >= 2
    assert body["first_break"] is None
    assert body["pre_chain_prefix"] == 0


def test_signing_updates_per_peer_chain_head(client: TestClient) -> None:
    _login(client)
    _login(client)

    events = list(reversed(client.get("/v1/audit?limit=10").json()))
    same_peer = [event for event in events if event["peer_id"] == events[-1]["peer_id"]]
    assert len(same_peer) >= 2
    latest = same_peer[-1]

    from uuid import UUID

    from sqlmodel import Session, select

    from target_workspace.api.signing import audit_event_hash
    from target_workspace.db import get_engine
    from target_workspace.db.tables import AuditChainHeadTable

    expected_head = audit_event_hash(
        event_id=latest["id"],
        peer_id=latest["peer_id"],
        prev_hash=latest["prev_hash"],
        actor_id=latest["actor_id"],
        event_type=latest["event_type"],
        target_id=latest["target_id"],
        occurred_at_iso=latest["occurred_at"],
        metadata=latest["metadata"],
        signature=latest["signature"],
    )
    with Session(get_engine()) as session:
        head = session.exec(
            select(AuditChainHeadTable).where(
                AuditChainHeadTable.peer_id == UUID(latest["peer_id"])
            )
        ).one_or_none()

    assert head is not None
    assert head.head_hash == expected_head


def test_audit_verify_reports_deleted_mid_chain_event(client: TestClient) -> None:
    _login(client)
    _login(client)
    _login(client)

    events = list(reversed(client.get("/v1/audit?limit=10").json()))
    same_peer = [event for event in events if event["peer_id"] == events[-1]["peer_id"]]
    assert len(same_peer) >= 3

    from uuid import UUID

    from sqlmodel import Session

    from target_workspace.db import get_engine
    from target_workspace.db.tables import AuditEventTable

    with Session(get_engine()) as session:
        row = session.get(AuditEventTable, UUID(same_peer[1]["id"]))
        assert row is not None
        session.delete(row)
        session.commit()

    verify = client.get("/v1/audit/verify")
    assert verify.status_code == 200, verify.text
    body = verify.json()
    assert body["ok"] is False
    assert body["first_break"]["reason"] == "broken_link"
    assert body["first_break"]["index"] >= 1
    assert body["first_break"]["expected_prev_hash"] != body["first_break"]["actual_prev_hash"]


def test_audit_verify_accepts_legacy_null_genesis_event(client: TestClient) -> None:
    from sqlmodel import Session, select

    from target_workspace.api.signing import sign_audit_event
    from target_workspace.db import get_engine
    from target_workspace.db.tables import AuditEventTable, UserTable

    occurred_at = datetime.now(tz=UTC) - timedelta(minutes=1)
    with Session(get_engine()) as session:
        user = session.exec(select(UserTable).where(UserTable.email == "admin@example.com")).one()
        old = AuditEventTable(
            workspace_id=user.workspace_id,
            actor_id=user.id,
            event_type="auth.login.success",
            occurred_at=occurred_at,
            metadata_json={"legacy": True},
        )
        session.add(old)
        session.flush()
        peer_id, sig, prev_hash = sign_audit_event(
            session,
            event_id=old.id,
            actor_id=old.actor_id,
            event_type=old.event_type,
            target_id=old.target_id,
            occurred_at=old.occurred_at,
            metadata=old.metadata_json,
            prev_hash=None,
        )
        assert prev_hash is None
        old.peer_id = peer_id
        old.signature = sig
        session.add(old)
        session.commit()

    _login(client)

    verify = client.get("/v1/audit/verify")
    assert verify.status_code == 200, verify.text
    body = verify.json()
    assert body["ok"] is True
    assert body["checked"] >= 2
    assert body["first_break"] is None
    assert body["pre_chain_prefix"] == 1


def test_audit_verify_accepts_multiple_legacy_null_prefix_events(
    client: TestClient,
) -> None:
    from sqlmodel import Session, select

    from target_workspace.api.signing import sign_audit_event
    from target_workspace.db import get_engine
    from target_workspace.db.tables import AuditEventTable, UserTable

    occurred_at = datetime.now(tz=UTC) - timedelta(minutes=2)
    with Session(get_engine()) as session:
        user = session.exec(select(UserTable).where(UserTable.email == "admin@example.com")).one()
        for offset_seconds in (0, 30):
            old = AuditEventTable(
                workspace_id=user.workspace_id,
                actor_id=user.id,
                event_type="auth.login.success",
                occurred_at=occurred_at + timedelta(seconds=offset_seconds),
                metadata_json={"legacy": True, "offset": offset_seconds},
            )
            session.add(old)
            session.flush()
            peer_id, sig, prev_hash = sign_audit_event(
                session,
                event_id=old.id,
                actor_id=old.actor_id,
                event_type=old.event_type,
                target_id=old.target_id,
                occurred_at=old.occurred_at,
                metadata=old.metadata_json,
                prev_hash=None,
            )
            assert prev_hash is None
            old.peer_id = peer_id
            old.signature = sig
            session.add(old)
        session.commit()

    _login(client)

    verify = client.get("/v1/audit/verify")
    assert verify.status_code == 200, verify.text
    body = verify.json()
    assert body["ok"] is True
    assert body["first_break"] is None
    assert body["pre_chain_prefix"] == 2


def test_legacy_unsigned_audit_rows_are_backfilled_into_the_chain(
    client: TestClient,
) -> None:
    from sqlmodel import Session, select

    from target_workspace.api.signing import backfill_legacy_audit_chain
    from target_workspace.db import get_engine
    from target_workspace.db.tables import AuditEventTable, UserTable

    occurred_at = datetime.now(tz=UTC) - timedelta(minutes=2)
    with Session(get_engine()) as session:
        user = session.exec(select(UserTable).where(UserTable.email == "admin@example.com")).one()
        legacy = AuditEventTable(
            workspace_id=user.workspace_id,
            actor_id=user.id,
            event_type="target.created",
            occurred_at=occurred_at,
            metadata_json={"legacy_unsigned": True},
        )
        session.add(legacy)
        session.commit()

    _login(client)

    verify_before = client.get("/v1/audit/verify").json()
    assert verify_before["ok"] is False
    assert verify_before["first_break"]["reason"] == "missing_signature"

    with Session(get_engine()) as session:
        backfilled = backfill_legacy_audit_chain(session)
        session.commit()

    assert backfilled >= 2

    verify_after = client.get("/v1/audit/verify")
    assert verify_after.status_code == 200, verify_after.text
    body = verify_after.json()
    assert body["ok"] is True
    assert body["checked"] >= 2
    assert body["first_break"] is None
    assert body["pre_chain_prefix"] == 0


def test_signature_verifies_against_instance_public_key(client: TestClient) -> None:
    _login(client)
    id_resp = client.get("/v1/instance/identity").json()
    pub = load_pem_public_key(id_resp["public_key_pem"].encode())
    assert isinstance(pub, Ed25519PublicKey)  # audit signing key is Ed25519

    events = client.get("/v1/audit?limit=10").json()
    assert events
    evt = events[0]

    from target_workspace.api.signing import canonical_payload

    payload = canonical_payload(
        event_id=evt["id"],
        peer_id=evt["peer_id"],
        prev_hash=evt.get("prev_hash"),
        actor_id=evt.get("actor_id"),
        event_type=evt["event_type"],
        target_id=evt.get("target_id"),
        occurred_at_iso=evt["occurred_at"],
        metadata=evt["metadata"],
    )

    import base64

    sig = base64.b64decode(evt["signature"])
    # Should not raise
    pub.verify(sig, payload)


def test_tampered_event_signature_fails_verification(client: TestClient) -> None:
    _login(client)
    id_resp = client.get("/v1/instance/identity").json()
    pub = load_pem_public_key(id_resp["public_key_pem"].encode())
    assert isinstance(pub, Ed25519PublicKey)  # audit signing key is Ed25519

    evt = client.get("/v1/audit?limit=10").json()[0]

    from target_workspace.api.signing import canonical_payload

    # Tamper with the event_type
    tampered = canonical_payload(
        event_id=evt["id"],
        peer_id=evt["peer_id"],
        prev_hash=evt.get("prev_hash"),
        actor_id=evt.get("actor_id"),
        event_type="auth.login.tampered",
        target_id=evt.get("target_id"),
        occurred_at_iso=evt["occurred_at"],
        metadata=evt["metadata"],
    )

    import base64

    sig = base64.b64decode(evt["signature"])
    with pytest.raises(InvalidSignature):
        pub.verify(sig, tampered)


def test_canonical_payload_binds_prev_hash() -> None:
    from target_workspace.api.signing import canonical_payload

    genesis = canonical_payload(
        event_id="event-1",
        peer_id="peer-1",
        prev_hash=None,
        actor_id=None,
        event_type="auth.login.success",
        target_id=None,
        occurred_at_iso="2026-06-04T14:00:00Z",
        metadata={},
    )
    chained = canonical_payload(
        event_id="event-1",
        peer_id="peer-1",
        prev_hash="abc123",
        actor_id=None,
        event_type="auth.login.success",
        target_id=None,
        occurred_at_iso="2026-06-04T14:00:00Z",
        metadata={},
    )

    assert genesis != chained
    assert b"|abc123|" in chained


def test_instance_identity_is_stable_across_calls(client: TestClient) -> None:
    a = client.get("/v1/instance/identity").json()
    b = client.get("/v1/instance/identity").json()
    assert a["peer_id"] == b["peer_id"]
    assert a["public_key_pem"] == b["public_key_pem"]
