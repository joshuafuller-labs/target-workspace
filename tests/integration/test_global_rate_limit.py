"""Global rate-limiting middleware (tw-bkd).

tw-b3bi shipped per-IP rate-limit on /v1/auth/login. This extends the
same in-memory sliding-window limiter to all write endpoints (POST/
PATCH/PUT/DELETE) globally, with a more generous default ceiling.

Goal: a misbehaving client (or scraper) can't take down the workspace
by hammering POST /v1/targets at 1000 req/sec. Read endpoints are NOT
rate-limited at MVP — only writes.

Assumption documented in tw-bkd:
  - Default: 120 writes / minute / IP. Configurable in v1.x.
  - Bypasses: auth.login already has its own tighter bucket (5/min).
  - Returns 429 with Retry-After.
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


def test_write_endpoint_429_after_threshold(client: TestClient) -> None:
    """Hammer a write endpoint past the global write threshold and expect 429."""
    # Lower the threshold via the LIMITS dict at runtime so this test
    # doesn't have to fire 120 POSTs.
    from target_workspace.api.ratelimit import LIMITS

    LIMITS["http.write.ip"] = (5, 60.0)  # 5 writes per minute for the test

    _login(client)
    # Use board creates as a cheap write target.
    statuses: list[int] = []
    for i in range(8):
        r = client.post(
            "/v1/boards",
            json={"name": f"B{i}", "columns": [{"name": "X", "order": 0}]},
        )
        statuses.append(r.status_code)

    assert any(s == 429 for s in statuses), f"expected 429 after threshold, got {statuses}"


def test_reads_are_not_rate_limited(client: TestClient) -> None:
    """GET endpoints are never globally rate-limited."""
    from target_workspace.api.ratelimit import LIMITS

    LIMITS["http.write.ip"] = (5, 60.0)
    _login(client)
    for _ in range(20):
        r = client.get("/v1/boards")
        assert r.status_code == 200, r.text


def test_auth_login_uses_own_bucket(client: TestClient) -> None:
    """Auth login has its own tighter bucket; global write limit doesn't
    double-charge it."""
    from target_workspace.api.ratelimit import LIMITS, reset_all

    reset_all()
    LIMITS["http.write.ip"] = (3, 60.0)  # very low
    # Login twice — should succeed (login has its own 5/min bucket).
    r1 = client.post(
        "/v1/auth/login",
        json={"email": "admin@example.com", "password": "test-pw"},
    )
    r2 = client.post(
        "/v1/auth/login",
        json={"email": "admin@example.com", "password": "test-pw"},
    )
    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text
