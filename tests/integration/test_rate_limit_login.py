"""Rate-limit /v1/auth/login per-IP (tw-b3bi).

MVP-scoped: in-memory sliding-window counter on login only. The other
auth endpoints called out in the ticket (forgot-password, reset-password,
mfa/verify) don't exist yet — they'll add their own limiter wiring
when they land.

Assumption documented in tw-b3bi:
  - In-memory store. Multi-instance deployments will need a shared
    backend (Redis) — that's a v1.1 follow-up.
  - 5 attempts per minute per IP. Configurable in v1.1.
  - 429 with Retry-After header, plus auth.rate_limited audit event.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.fast]

LIMIT = 5


def test_login_within_limit_succeeds(client: TestClient) -> None:
    for _ in range(LIMIT):
        r = client.post(
            "/v1/auth/login",
            json={"email": "admin@example.com", "password": "test-pw"},
        )
        # Either 200 (first call) or 200 still after limit because we're
        # under threshold. (TestClient reuses one transport so cookies
        # are sent on subsequent calls — but the endpoint still runs.)
        assert r.status_code in (200, 401), r.text


def test_login_exceeding_limit_returns_429_with_retry_after(
    client: TestClient,
) -> None:
    # Exhaust the limit with failing attempts so we don't accidentally
    # short-circuit on already-authenticated state.
    for _ in range(LIMIT):
        client.post(
            "/v1/auth/login",
            json={"email": "noone@example.com", "password": "wrong"},
        )

    r = client.post(
        "/v1/auth/login",
        json={"email": "noone@example.com", "password": "wrong"},
    )
    assert r.status_code == 429, r.text
    assert "Retry-After" in r.headers


def test_rate_limit_emits_audit_event(client: TestClient) -> None:
    for _ in range(LIMIT):
        client.post(
            "/v1/auth/login",
            json={"email": "noone@example.com", "password": "wrong"},
        )
    client.post(
        "/v1/auth/login",
        json={"email": "noone@example.com", "password": "wrong"},
    )

    # Log in as admin to read audit. Need to RESET the limiter first
    # since admin login would also be blocked.
    from target_workspace.api.ratelimit import reset_all

    reset_all()

    client.post(
        "/v1/auth/login",
        json={"email": "admin@example.com", "password": "test-pw"},
    )
    events = client.get("/v1/audit?limit=200").json()
    limited = [e for e in events if e["event_type"] == "auth.rate_limited"]
    assert len(limited) >= 1, (
        f"expected auth.rate_limited audit event, got auth.*: "
        f"{[e for e in events if e['event_type'].startswith('auth.')]}"
    )
