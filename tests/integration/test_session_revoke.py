"""Session management — revoke-all + auto-revoke on password change (tw-ptn2).

MVP scope: a single `user.session_version` integer on the user row,
included in the signed cookie. Bumping the version invalidates every
existing cookie for that user.

Assumption documented in tw-ptn2:
  - Listing active sessions (GET /v1/auth/sessions), revoking a specific
    session (DELETE /v1/auth/sessions/{id}), and last_seen tracking
    require a sessions table; deferred to v1.1.
  - revoke-all + auto-revoke-on-password-change are the
    security-incident-response affordances; ship those alone.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.fast]


def _login(c: TestClient) -> None:
    r = c.post("/v1/auth/login", json={"email": "admin@example.com", "password": "test-pw"})
    assert r.status_code == 200, r.text


def test_revoke_all_invalidates_other_sessions(client: TestClient) -> None:
    _login(client)
    # Capture the original cookie
    cookie = client.cookies.get("tw_session")
    assert cookie

    # Revoke-all — this bumps user.session_version
    r = client.post("/v1/auth/sessions/revoke-all")
    assert r.status_code == 200, r.text

    # A second client using the OLD cookie should be rejected
    from fastapi.testclient import TestClient as _TC

    other = _TC(client.app)
    other.cookies.set("tw_session", cookie)
    r = other.get("/v1/auth/me")
    assert r.status_code == 401, r.text


def test_password_change_auto_revokes_sessions(client: TestClient) -> None:
    # Create a user we can manipulate
    _login(client)
    r = client.post(
        "/v1/users",
        json={
            "email": "rotate@example.com",
            "display_name": "Rotator",
            "role": "operator",
            "password": "first-pw",
        },
    )
    assert r.status_code == 201
    client.post("/v1/auth/logout")

    # Login as the rotator, capture cookie
    client.post(
        "/v1/auth/login",
        json={"email": "rotate@example.com", "password": "first-pw"},
    )
    cookie_before = client.cookies.get("tw_session")
    assert cookie_before

    # Change password — this should auto-revoke sessions.
    r = client.post(
        "/v1/auth/change-password",
        json={"current_password": "first-pw", "new_password": "rotated-pw"},
    )
    assert r.status_code == 200, r.text

    # The pre-change cookie should now be rejected.
    from fastapi.testclient import TestClient as _TC

    stale = _TC(client.app)
    stale.cookies.set("tw_session", cookie_before)
    r = stale.get("/v1/auth/me")
    assert r.status_code == 401, r.text


def test_revoke_all_emits_audit_event(client: TestClient) -> None:
    _login(client)
    client.post("/v1/auth/sessions/revoke-all")
    # Need to log back in since revoke-all invalidated our session too.
    _login(client)
    events = client.get("/v1/audit?limit=200").json()
    revoked = [e for e in events if e["event_type"] == "auth.sessions.revoked"]
    assert len(revoked) >= 1


def test_revoke_all_requires_auth(client: TestClient) -> None:
    r = client.post("/v1/auth/sessions/revoke-all")
    assert r.status_code == 401
