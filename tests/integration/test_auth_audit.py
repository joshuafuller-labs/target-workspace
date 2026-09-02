"""Auth telemetry audit log (tw-6llq).

Records every authentication event (login success, login failure, logout)
into the existing audit_event table with auth.* event types. Compliance
foundation (CJIS / FedRAMP / RMF reporting).

Schema decisions (assumption documented in tw-6llq):
  - audit_event.target_id becomes nullable (auth events have no target)
  - audit_event.actor_id becomes nullable (failed-login-on-unknown-email
    has no actor)
  - Failed logins are logged against the single default workspace when
    the email doesn't match any user; against the user's workspace when
    it does.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.fast]


def _auth_events(client: TestClient) -> list[dict[str, Any]]:
    """Fetch all audit events, filter to auth.* types client-side.

    Listing endpoint requires authentication; caller logs in first.
    """
    r = client.get("/v1/audit?limit=200")
    assert r.status_code == 200, r.text
    return [e for e in r.json() if e["event_type"].startswith("auth.")]


def test_successful_login_emits_auth_login_success(client: TestClient) -> None:
    r = client.post(
        "/v1/auth/login",
        json={"email": "admin@example.com", "password": "test-pw"},
    )
    assert r.status_code == 200, r.text

    events = _auth_events(client)
    success = [e for e in events if e["event_type"] == "auth.login.success"]
    assert len(success) >= 1, f"expected auth.login.success, got events={events}"
    evt = success[-1]
    assert evt["actor_id"] is not None
    # target_id may be None for auth events
    assert evt.get("target_id") is None


def test_failed_login_wrong_password_emits_auth_login_failed(
    client: TestClient,
) -> None:
    # Try with a known email but wrong password
    r = client.post(
        "/v1/auth/login",
        json={"email": "admin@example.com", "password": "wrong-password"},
    )
    assert r.status_code == 401

    # Then log in successfully so we can query the audit log
    client.post(
        "/v1/auth/login",
        json={"email": "admin@example.com", "password": "test-pw"},
    )
    events = _auth_events(client)
    failed = [e for e in events if e["event_type"] == "auth.login.failed"]
    assert len(failed) >= 1, f"expected auth.login.failed, got events={events}"


def test_failed_login_unknown_email_emits_auth_login_failed(
    client: TestClient,
) -> None:
    # Attempt with an email that doesn't match any user
    r = client.post(
        "/v1/auth/login",
        json={"email": "ghost@example.com", "password": "irrelevant"},
    )
    assert r.status_code == 401

    # Log in as admin to query audit
    client.post(
        "/v1/auth/login",
        json={"email": "admin@example.com", "password": "test-pw"},
    )
    events = _auth_events(client)
    failed = [e for e in events if e["event_type"] == "auth.login.failed"]
    # Two failed: one from this test
    assert len(failed) >= 1
    # The unknown-email failure has actor_id None (no matching user)
    unknown_actor = [e for e in failed if e["actor_id"] is None]
    assert len(unknown_actor) >= 1, (
        f"expected at least one failed login with actor_id=None, got {failed}"
    )


def test_logout_emits_auth_logout(client: TestClient) -> None:
    client.post(
        "/v1/auth/login",
        json={"email": "admin@example.com", "password": "test-pw"},
    )
    r = client.post("/v1/auth/logout")
    assert r.status_code == 200

    # Log back in to query
    client.post(
        "/v1/auth/login",
        json={"email": "admin@example.com", "password": "test-pw"},
    )
    events = _auth_events(client)
    logout = [e for e in events if e["event_type"] == "auth.logout"]
    assert len(logout) >= 1
