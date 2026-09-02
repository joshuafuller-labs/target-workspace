"""Audit-log filtering extensions (tw-81p).

Adds query params to /v1/audit:
  - actor_id    filter by who triggered
  - event_type  filter by event type
  - q           full-text search in justification + metadata
  - from        ISO datetime, lower bound (occurred_at >= from)
  - to          ISO datetime, upper bound (occurred_at <= to)

Existing `since` + `cursor` continue to work; new params compose.

Export endpoint: GET /v1/audit/export.csv returns a CSV download
of the filtered set, capped at 10_000 rows.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.fast]


def _login(c: TestClient) -> dict[str, Any]:
    r = c.post("/v1/auth/login", json={"email": "admin@example.com", "password": "test-pw"})
    return r.json()


def _seed_audit(c: TestClient) -> None:
    """Create several targets + moves so we have a mix of events."""
    b = c.post(
        "/v1/boards",
        json={
            "name": "B",
            "columns": [
                {"name": "A", "order": 0},
                {"name": "B", "order": 1},
            ],
        },
    ).json()
    for n in ("alpha", "bravo", "charlie"):
        c.post(
            "/v1/capture",
            data={
                "title": n,
                "lat": "35.6",
                "lon": "-82.55",
                "board_id": b["id"],
                "column_id": b["columns"][0]["id"],
            },
        )


def test_filter_by_event_type(client: TestClient) -> None:
    _login(client)
    _seed_audit(client)
    # auth.login.success is reliably emitted by _login; use it as a
    # canonical event type for the filter probe.
    r = client.get("/v1/audit?event_type=auth.login.success&limit=100")
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) >= 1
    assert all(e["event_type"] == "auth.login.success" for e in rows)


def test_filter_by_actor_id(client: TestClient) -> None:
    me = _login(client)
    _seed_audit(client)
    r = client.get(f"/v1/audit?actor_id={me['id']}&limit=100")
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) >= 1
    assert all(e["actor_id"] == me["id"] for e in rows if e.get("actor_id"))


def test_filter_by_time_window(client: TestClient) -> None:
    _login(client)
    _seed_audit(client)
    # An impossibly-future 'from' should return zero rows.
    r = client.get("/v1/audit?from=2099-01-01T00:00:00&limit=100")
    assert r.status_code == 200, r.text
    assert r.json() == []


def test_filter_by_text_search(client: TestClient) -> None:
    """q matches inside metadata JSON (case-insensitive substring).

    The admin email lands in auth.login.success metadata, so a search
    for 'admin' should hit at least the login event.
    """
    _login(client)
    _seed_audit(client)
    r = client.get("/v1/audit?q=admin&limit=100")
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) >= 1
    assert any("admin" in str(e.get("metadata") or {}).lower() for e in rows)


def test_export_csv(client: TestClient) -> None:
    _login(client)
    _seed_audit(client)
    r = client.get("/v1/audit/export.csv")
    assert r.status_code == 200, r.text
    assert "text/csv" in r.headers["content-type"]
    body = r.text
    # Header row
    lines = body.strip().split("\n")
    assert lines[0].startswith("id,occurred_at,event_type,actor_id")
    # At least one data row
    assert len(lines) >= 2


def test_export_csv_respects_filters(client: TestClient) -> None:
    _login(client)
    _seed_audit(client)
    r = client.get("/v1/audit/export.csv?event_type=auth.login.success")
    assert r.status_code == 200, r.text
    body = r.text
    lines = body.strip().split("\n")
    # All non-header lines have event_type=auth.login.success
    for line in lines[1:]:
        assert "auth.login.success" in line
