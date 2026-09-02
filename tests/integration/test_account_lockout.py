"""Account lockout after N failed login attempts (tw-gmq7).

After N=10 failed login attempts in a rolling 15-minute window, the
account is locked for 30 minutes. Lock is recorded via locked_until
on user + auth.account.locked audit event. Admin can manually unlock.

Assumption documented in tw-gmq7:
  - Failed attempts are counted by querying recent auth.login.failed
    events from the audit log for this user. Avoids a separate
    failed_login_attempt table at MVP.
  - Per-IP rate-limit is post-MVP (covered by tw-b3bi). This ticket is
    per-user lockout only.
  - N, window, and cooldown are hard-coded at MVP; configurable in v1.x.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.fast]

LOCKOUT_THRESHOLD = 10


def _create_user(c: TestClient) -> dict[str, Any]:
    c.post("/v1/auth/login", json={"email": "admin@example.com", "password": "test-pw"})
    r = c.post(
        "/v1/users",
        json={
            "email": "lockme@example.com",
            "display_name": "Lock Me",
            "role": "operator",
            "password": "correct-pw",
        },
    )
    assert r.status_code == 201, r.text
    c.post("/v1/auth/logout")
    return r.json()


def _attempt_login(c: TestClient, *, password: str) -> int:
    # Reset the per-IP rate limiter on each attempt so this test exercises
    # the lockout threshold (tw-gmq7) independent of the rate limit (tw-b3bi).
    from target_workspace.api.ratelimit import reset_all

    reset_all()
    return c.post(
        "/v1/auth/login",
        json={"email": "lockme@example.com", "password": password},
    ).status_code


def test_threshold_failed_logins_locks_account(client: TestClient) -> None:
    _create_user(client)
    # Fail the threshold times with the wrong password
    for _ in range(LOCKOUT_THRESHOLD):
        assert _attempt_login(client, password="wrong") == 401

    # The next attempt — even with the CORRECT password — must be rejected
    # because the account is now locked.
    assert _attempt_login(client, password="correct-pw") == 401


def test_lockout_emits_audit_event(client: TestClient) -> None:
    _create_user(client)
    for _ in range(LOCKOUT_THRESHOLD):
        _attempt_login(client, password="wrong")

    client.post("/v1/auth/login", json={"email": "admin@example.com", "password": "test-pw"})
    events = client.get("/v1/audit?limit=200").json()
    locked = [e for e in events if e["event_type"] == "auth.account.locked"]
    assert len(locked) >= 1, (
        f"expected auth.account.locked, got auth.*: "
        f"{[e for e in events if e['event_type'].startswith('auth.')]}"
    )


def test_admin_can_unlock_account(client: TestClient) -> None:
    new_user = _create_user(client)
    for _ in range(LOCKOUT_THRESHOLD):
        _attempt_login(client, password="wrong")
    # Confirm locked
    assert _attempt_login(client, password="correct-pw") == 401

    # Admin unlocks
    client.post("/v1/auth/login", json={"email": "admin@example.com", "password": "test-pw"})
    r = client.post(f"/v1/users/{new_user['id']}/unlock")
    assert r.status_code == 200, r.text
    client.post("/v1/auth/logout")

    # Now the correct password should work — but the user still has
    # must_change_password=True from tw-4exk, so we get 200 + the flag.
    assert _attempt_login(client, password="correct-pw") == 200


def test_unlock_admin_only(client: TestClient) -> None:
    new_user = _create_user(client)
    # No admin login — unauthenticated unlock attempt
    r = client.post(f"/v1/users/{new_user['id']}/unlock")
    assert r.status_code == 401
