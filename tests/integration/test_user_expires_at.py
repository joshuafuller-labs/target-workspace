"""Time-bound user access (tw-6to0).

When an admin sets user.expires_at in the past, that user is locked out
of every authenticated endpoint with a 401. Login itself also rejects.

Assumption documented in tw-6to0:
  - group_member.expires_at is deferred to tw-icj8 (workspace groups
    ship together as a unit). MVP covers the user-level expiry only.
  - SPA banner for 'access expires in 24hr' is frontend polish, deferred.
  - Audit event 'auth.access.expired' is emitted on EACH rejection
    (de-duping per session is post-MVP polish).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.fast]


def _login_admin(c: TestClient) -> None:
    r = c.post("/v1/auth/login", json={"email": "admin@example.com", "password": "test-pw"})
    assert r.status_code == 200, r.text


def _create_user(c: TestClient, *, expires_at: str | None = None) -> dict[str, Any]:
    body = {
        "email": "expiring@example.com",
        "display_name": "Expiring User",
        "role": "operator",
        "password": "temp-pw-123",
    }
    if expires_at is not None:
        body["expires_at"] = expires_at
    r = c.post("/v1/users", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_user_with_future_expiry_can_login(client: TestClient) -> None:
    _login_admin(client)
    future = (datetime.now(tz=UTC) + timedelta(hours=72)).isoformat().replace("+00:00", "Z")
    _create_user(client, expires_at=future)
    client.post("/v1/auth/logout")

    r = client.post(
        "/v1/auth/login",
        json={"email": "expiring@example.com", "password": "temp-pw-123"},
    )
    assert r.status_code == 200, r.text


def test_user_with_past_expiry_cannot_login(client: TestClient) -> None:
    _login_admin(client)
    past = (datetime.now(tz=UTC) - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    _create_user(client, expires_at=past)
    client.post("/v1/auth/logout")

    r = client.post(
        "/v1/auth/login",
        json={"email": "expiring@example.com", "password": "temp-pw-123"},
    )
    assert r.status_code == 401, r.text


def test_user_with_null_expiry_unaffected(client: TestClient) -> None:
    _login_admin(client)
    _create_user(client, expires_at=None)
    client.post("/v1/auth/logout")
    r = client.post(
        "/v1/auth/login",
        json={"email": "expiring@example.com", "password": "temp-pw-123"},
    )
    assert r.status_code == 200, r.text


def test_admin_can_set_expires_at_via_patch(client: TestClient) -> None:
    _login_admin(client)
    new_user = _create_user(client, expires_at=None)
    past = (datetime.now(tz=UTC) - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    r = client.patch(f"/v1/users/{new_user['id']}", json={"expires_at": past})
    assert r.status_code == 200, r.text
    # Now this user can't log in.
    client.post("/v1/auth/logout")
    r = client.post(
        "/v1/auth/login",
        json={"email": "expiring@example.com", "password": "temp-pw-123"},
    )
    assert r.status_code == 401, r.text


def test_expired_login_emits_audit_event(client: TestClient) -> None:
    _login_admin(client)
    past = (datetime.now(tz=UTC) - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    _create_user(client, expires_at=past)
    client.post("/v1/auth/logout")
    client.post(
        "/v1/auth/login",
        json={"email": "expiring@example.com", "password": "temp-pw-123"},
    )

    _login_admin(client)
    events = client.get("/v1/audit?limit=200").json()
    expired = [
        e
        for e in events
        if e["event_type"] in ("auth.access.expired", "auth.login.failed")
        and (e["metadata"] or {}).get("reason") == "expired"
    ]
    assert len(expired) >= 1, (
        f"expected an expired-access audit event, got events with auth.* types: "
        f"{[e for e in events if e['event_type'].startswith('auth.')]}"
    )
