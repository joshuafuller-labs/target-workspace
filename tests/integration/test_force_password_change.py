"""Force password change on first login (tw-4exk).

When a commander provisions a new user with a temp password, the
user.must_change_password flag is set. The new user can log in and
hit /v1/auth/* endpoints, but every other route returns 403 until
they POST /v1/auth/change-password with a new password.

The bootstrap admin (created from env var on first boot) does NOT
get the flag — they aren't admin-provisioned.

Assumption documented in tw-4exk:
  - Admin-resetting another user's password (PATCH /v1/users/{id})
    setting must_change_password=True is a follow-up; this ticket
    covers the creation path only.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.fast]


def _login_as_admin(client: TestClient) -> None:
    r = client.post(
        "/v1/auth/login",
        json={"email": "admin@example.com", "password": "test-pw"},
    )
    assert r.status_code == 200, r.text


def _create_user(
    client: TestClient,
    *,
    email: str = "newby@example.com",
    password: str = "temp-pass-123",
    role: str = "operator",
) -> dict[str, Any]:
    r = client.post(
        "/v1/users",
        json={
            "email": email,
            "display_name": "New B. User",
            "role": role,
            "password": password,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_bootstrap_admin_does_not_require_password_change(
    client: TestClient,
) -> None:
    _login_as_admin(client)
    # The admin can hit a non-auth route normally — no forced change.
    r = client.get("/v1/boards")
    assert r.status_code == 200


def test_new_user_login_succeeds_but_must_change_flag_set(
    client: TestClient,
) -> None:
    _login_as_admin(client)
    _create_user(client)
    client.post("/v1/auth/logout")

    r = client.post(
        "/v1/auth/login",
        json={"email": "newby@example.com", "password": "temp-pass-123"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("must_change_password") is True


def test_new_user_blocked_from_non_auth_routes_until_change(
    client: TestClient,
) -> None:
    _login_as_admin(client)
    _create_user(client)
    client.post("/v1/auth/logout")

    client.post(
        "/v1/auth/login",
        json={"email": "newby@example.com", "password": "temp-pass-123"},
    )
    # /v1/auth/me is allowed (auth route).
    me = client.get("/v1/auth/me")
    assert me.status_code == 200

    # /v1/boards is NOT allowed until password is changed.
    r = client.get("/v1/boards")
    assert r.status_code == 403, r.text
    assert "password" in r.json().get("detail", "").lower()


def test_change_password_clears_flag_and_unlocks_routes(client: TestClient) -> None:
    _login_as_admin(client)
    _create_user(client)
    client.post("/v1/auth/logout")

    client.post(
        "/v1/auth/login",
        json={"email": "newby@example.com", "password": "temp-pass-123"},
    )

    # Change the password.
    r = client.post(
        "/v1/auth/change-password",
        json={"current_password": "temp-pass-123", "new_password": "new-strong-pass-456"},
    )
    assert r.status_code == 200, r.text

    # Now boards is reachable.
    r = client.get("/v1/boards")
    assert r.status_code == 200, r.text

    # And /v1/auth/me confirms the flag is cleared.
    me = client.get("/v1/auth/me")
    assert me.json().get("must_change_password") is False


def test_change_password_with_wrong_current_rejected(client: TestClient) -> None:
    _login_as_admin(client)
    _create_user(client)
    client.post("/v1/auth/logout")
    client.post(
        "/v1/auth/login",
        json={"email": "newby@example.com", "password": "temp-pass-123"},
    )
    r = client.post(
        "/v1/auth/change-password",
        json={"current_password": "wrong-current", "new_password": "new-strong-pass-456"},
    )
    assert r.status_code == 401, r.text


def test_change_password_emits_audit_event(client: TestClient) -> None:
    _login_as_admin(client)
    _create_user(client)
    client.post("/v1/auth/logout")
    client.post(
        "/v1/auth/login",
        json={"email": "newby@example.com", "password": "temp-pass-123"},
    )
    client.post(
        "/v1/auth/change-password",
        json={"current_password": "temp-pass-123", "new_password": "new-strong-pass-456"},
    )

    events = client.get("/v1/audit?limit=200").json()
    changed = [e for e in events if e["event_type"] == "auth.password.changed"]
    assert len(changed) >= 1
