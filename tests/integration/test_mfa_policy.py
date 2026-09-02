"""Workspace MFA-enforcement policy (tw-r1ru).

Admin sets which roles MUST have totp_enabled before they can be
granted. Default: no requirement. When set, role promotion through
PATCH /v1/users/{id} returns 409 if the target lacks MFA.

Endpoints:
  GET /v1/workspace/mfa-policy        → { required_for_roles: [...] }
  PUT /v1/workspace/mfa-policy { required_for_roles: [...] } → 200
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.fast]


def _login(c: TestClient, email: str = "admin@example.com", pw: str = "test-pw") -> None:
    r = c.post("/v1/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text


def test_default_policy_is_empty(client: TestClient) -> None:
    _login(client)
    r = client.get("/v1/workspace/mfa-policy")
    assert r.status_code == 200, r.text
    assert r.json() == {"required_for_roles": []}


def test_admin_can_set_policy(client: TestClient) -> None:
    _login(client)
    r = client.put(
        "/v1/workspace/mfa-policy",
        json={"required_for_roles": ["admin", "commander"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["required_for_roles"] == ["admin", "commander"]
    # Persisted
    r2 = client.get("/v1/workspace/mfa-policy")
    assert r2.json()["required_for_roles"] == ["admin", "commander"]


def test_policy_rejects_unknown_role(client: TestClient) -> None:
    _login(client)
    r = client.put(
        "/v1/workspace/mfa-policy",
        json={"required_for_roles": ["totally-bogus"]},
    )
    assert r.status_code == 422


def test_promoting_user_without_mfa_blocked(client: TestClient) -> None:
    _login(client)
    # Set policy
    client.put(
        "/v1/workspace/mfa-policy",
        json={"required_for_roles": ["commander"]},
    )
    # Create operator user (no MFA)
    user = client.post(
        "/v1/users",
        json={
            "email": "op@example.com",
            "display_name": "Operator",
            "role": "operator",
            "password": "tmp-pass-123",
        },
    ).json()
    # Try to promote them to commander — should 409
    r = client.patch(
        f"/v1/users/{user['id']}",
        json={"role": "commander"},
    )
    assert r.status_code == 409, r.text
    assert "mfa" in r.text.lower() or "MFA" in r.text


def test_promoting_user_with_mfa_succeeds(client: TestClient) -> None:
    """Once the target user has totp_enabled, they can hold the role."""
    _login(client)
    client.put(
        "/v1/workspace/mfa-policy",
        json={"required_for_roles": ["commander"]},
    )
    user = client.post(
        "/v1/users",
        json={
            "email": "op@example.com",
            "display_name": "Operator",
            "role": "operator",
            "password": "tmp-pass-123",
        },
    ).json()
    # Directly mark MFA on the user via the configured DB.
    from sqlmodel import Session, select

    from target_workspace.db import get_engine
    from target_workspace.db.tables import UserTable

    with Session(get_engine()) as s:
        u = s.exec(select(UserTable).where(UserTable.email == "op@example.com")).first()
        assert u is not None
        u.totp_enabled = True
        u.totp_secret = "AAAAAAAAAA"
        s.add(u)
        s.commit()

    r = client.patch(
        f"/v1/users/{user['id']}",
        json={"role": "commander"},
    )
    assert r.status_code == 200, r.text


def test_only_admin_can_set_policy(client: TestClient) -> None:
    """A non-admin should not be able to mutate the policy."""
    _login(client)
    # Create a viewer
    client.post(
        "/v1/users",
        json={
            "email": "v@example.com",
            "display_name": "Viewer",
            "role": "viewer",
            "password": "tmp-pass-123",
        },
    )
    client.post("/v1/auth/logout")
    _login(client, email="v@example.com", pw="tmp-pass-123")
    r = client.put(
        "/v1/workspace/mfa-policy",
        json={"required_for_roles": ["admin"]},
    )
    assert r.status_code in (401, 403)
