"""Invitation flow — coordinator-mintable join tokens (tw-qmnh).

Sub-org coordinator generates a token, shares the URL out-of-band
(Signal / SMS / printout), recipient creates their account by POSTing
to /v1/auth/redeem-invitation.

Assumption documented in tw-qmnh:
  - Tokens are sha256-hashed at rest (never stored in plaintext).
  - Group association (invitation.group_id) is deferred until tw-icj8
    ships the groups schema. MVP issues workspace-level invitations
    only.
  - Email delivery deferred (rides on tw-qj9k email backend). The token
    is returned to the issuer ONCE in the response; they're responsible
    for OOB sharing.
  - Default expiry 72h, max_uses 1.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.fast]


def _login_admin(c: TestClient) -> None:
    r = c.post("/v1/auth/login", json={"email": "admin@example.com", "password": "test-pw"})
    assert r.status_code == 200, r.text


def test_commander_can_issue_invitation_and_recipient_can_redeem(
    client: TestClient,
) -> None:
    _login_admin(client)
    r = client.post("/v1/invitations", json={"role": "operator"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert "token" in body, body
    assert "expires_at" in body
    raw_token = body["token"]
    assert len(raw_token) >= 32

    client.post("/v1/auth/logout")
    r = client.post(
        "/v1/auth/redeem-invitation",
        json={
            "token": raw_token,
            "email": "joiner@example.com",
            "display_name": "New Joiner",
            "password": "joiner-pw-123",  # gitleaks:allow -- test-only password
        },
    )
    assert r.status_code == 201, r.text
    new_user = r.json()
    assert new_user["email"] == "joiner@example.com"
    assert new_user["role"] == "operator"


def test_invitation_single_use_second_redemption_fails(client: TestClient) -> None:
    _login_admin(client)
    raw_token = client.post(
        "/v1/invitations",
        json={"role": "viewer"},
    ).json()["token"]
    client.post("/v1/auth/logout")

    r1 = client.post(
        "/v1/auth/redeem-invitation",
        json={
            "token": raw_token,
            "email": "first@example.com",
            "display_name": "First",
            "password": "test-pass",
        },
    )
    assert r1.status_code == 201

    r2 = client.post(
        "/v1/auth/redeem-invitation",
        json={
            "token": raw_token,
            "email": "second@example.com",
            "display_name": "Second",
            "password": "test-pass",
        },
    )
    assert r2.status_code == 409, r2.text


def test_unknown_token_rejected(client: TestClient) -> None:
    r = client.post(
        "/v1/auth/redeem-invitation",
        json={
            "token": "z" * 64,
            "email": "noone@example.com",
            "display_name": "No One",
            "password": "test-pass",
        },
    )
    assert r.status_code == 404, r.text


def test_admin_only_can_issue(client: TestClient) -> None:
    r = client.post("/v1/invitations", json={"role": "viewer"})
    assert r.status_code == 401, r.text


def test_redeemed_user_must_change_password_on_first_login(
    client: TestClient,
) -> None:
    """Per tw-4exk: tokens are equivalent to admin-provisioning, so the
    redeemer hits the must-change-password gate on first login."""
    _login_admin(client)
    raw_token = client.post(
        "/v1/invitations",
        json={"role": "operator"},
    ).json()["token"]
    client.post("/v1/auth/logout")

    client.post(
        "/v1/auth/redeem-invitation",
        json={
            "token": raw_token,
            "email": "newhire@example.com",
            "display_name": "New Hire",
            "password": "first-password",
        },
    )
    # The redemption creates an authenticated session AND sets the
    # must-change-password flag.
    me = client.get("/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["must_change_password"] is True
