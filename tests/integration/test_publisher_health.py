"""Publisher / TAK-server connection health (tw-mowp).

GET /v1/publishers/health → list of {publisher_id, name, plugin_type,
  enabled, last_publish_at, last_error, error_count_1m, publish_count_1m}

Reads from a small in-memory ring of recent publish events. The
publisher dispatcher (tw-50i5) records into this ring on every emit.

Assumption documented in tw-mowp:
  - 1-minute sliding window for rate. Simple per-publisher deque of
    timestamps; ages out on read.
  - PLI rate per-server (subset of publish rate) is post-MVP — the
    cot-in side feeds it through tw-6uz8 cache for now.
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


def test_no_publishers_returns_empty_list(client: TestClient) -> None:
    _login(client)
    r = client.get("/v1/publishers/health")
    assert r.status_code == 200, r.text
    assert r.json() == []


def test_records_publish_event_in_health(client: TestClient) -> None:
    from target_workspace.api.publisher_health import (
        record_publish_success,
    )

    _login(client)
    record_publish_success(
        publisher_id="00000000-0000-0000-0000-000000000001",
        name="tak-prod",
        plugin_type="tak_server",
    )
    r = client.get("/v1/publishers/health").json()
    assert len(r) == 1
    assert r[0]["name"] == "tak-prod"
    assert r[0]["publish_count_1m"] >= 1
    assert r[0]["last_error"] is None


def test_records_failure_in_health(client: TestClient) -> None:
    from target_workspace.api.publisher_health import (
        record_publish_failure,
    )

    _login(client)
    record_publish_failure(
        publisher_id="00000000-0000-0000-0000-000000000002",
        name="tak-failing",
        plugin_type="tak_server",
        error="connection refused",
    )
    r = client.get("/v1/publishers/health").json()
    failing = [p for p in r if p["name"] == "tak-failing"]
    assert len(failing) == 1
    assert failing[0]["last_error"] == "connection refused"
    assert failing[0]["error_count_1m"] >= 1


def test_health_requires_auth(client: TestClient) -> None:
    r = client.get("/v1/publishers/health")
    assert r.status_code == 401
