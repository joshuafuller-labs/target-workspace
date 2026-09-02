"""Empty-state demo scenario discovery (tw-jxl).

GET /v1/workspace/demo-scenarios → list of bundled scenarios the SPA
can offer as load-buttons on the empty-state path (no boards yet).

Assumption documented in tw-jxl:
  - Endpoint requires auth. SPA reads it after login when boards
    list returns empty.
  - 'Load scenario' (POST) is a separate ticket; this is read-only
    discovery.
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


def test_demo_scenarios_returns_list(client: TestClient) -> None:
    _login(client)
    r = client.get("/v1/workspace/demo-scenarios")
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, list)
    # At least one scenario should ship bundled (TF DAGGER F3EAD).
    assert len(body) >= 1
    first = body[0]
    assert "id" in first
    assert "name" in first


def test_demo_scenarios_requires_auth(client: TestClient) -> None:
    r = client.get("/v1/workspace/demo-scenarios")
    assert r.status_code == 401
