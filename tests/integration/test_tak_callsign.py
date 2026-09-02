"""User ↔ TAK callsign mapping (tw-tl9r).

users.tak_callsign string column (nullable, unique per workspace).
Lets the workspace bind PLI to a user identity without re-issuing
auth.

Assumption documented in tw-tl9r:
  - Uniqueness is workspace-scoped, not global. Multiple workspaces
    on one instance (if/when multi-tenancy lands) can each have a
    'BISON-01'.
  - PATCH /v1/users/{id} accepts tak_callsign. /v1/auth/me returns it.
  - Validation: 1-32 chars, alphanumeric + dash. Reasonable for
    real TAK callsigns; no special-char hostility.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.fast]


def _login(c: TestClient) -> None:
    r = c.post(
        "/v1/auth/login",
        json={"email": "admin@example.com", "password": "test-pw"},
    )
    assert r.status_code == 200, r.text


def test_user_has_no_callsign_by_default(client: TestClient) -> None:
    _login(client)
    me = client.get("/v1/auth/me").json()
    assert me.get("tak_callsign") is None


def test_admin_can_set_user_callsign_via_patch(client: TestClient) -> None:
    _login(client)
    new_user = client.post(
        "/v1/users",
        json={
            "email": "operator@example.com",
            "display_name": "Op",
            "role": "operator",
            "password": "test-pass",
        },
    ).json()
    r = client.patch(
        f"/v1/users/{new_user['id']}",
        json={"tak_callsign": "BISON-01"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["tak_callsign"] == "BISON-01"


def test_callsign_unique_within_workspace(client: TestClient) -> None:
    _login(client)
    a = client.post(
        "/v1/users",
        json={
            "email": "a@example.com",
            "display_name": "A",
            "role": "viewer",
            "password": "test-pass",
        },
    ).json()
    b = client.post(
        "/v1/users",
        json={
            "email": "b@example.com",
            "display_name": "B",
            "role": "viewer",
            "password": "test-pass",
        },
    ).json()
    client.patch(f"/v1/users/{a['id']}", json={"tak_callsign": "WOLF-02"})
    r = client.patch(f"/v1/users/{b['id']}", json={"tak_callsign": "WOLF-02"})
    assert r.status_code == 409, r.text


def test_callsign_validation_rejects_bad_input(client: TestClient) -> None:
    _login(client)
    me = client.get("/v1/auth/me").json()
    # Too long
    r = client.patch(
        f"/v1/users/{me['id']}",
        json={"tak_callsign": "X" * 64},
    )
    assert r.status_code == 422


def test_clear_callsign_via_null(client: TestClient) -> None:
    _login(client)
    me = client.get("/v1/auth/me").json()
    client.patch(f"/v1/users/{me['id']}", json={"tak_callsign": "BISON-01"})
    r = client.patch(f"/v1/users/{me['id']}", json={"tak_callsign": None})
    assert r.status_code == 200
    assert r.json()["tak_callsign"] is None
