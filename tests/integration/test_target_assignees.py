"""Target assignees — assigned_callsigns field + assign/unassign API (tw-5kqh).

Schema column on target + lightweight assign / unassign endpoints.
UI affordances (chip rendering, autocomplete from PLI cache) defer
to v1.x.

Assumption documented in tw-5kqh:
  - Callsigns are free-form strings at MVP — no FK to a roster.
    User-callsign mapping (tw-tl9r) will validate references in v1.x.
  - Assign / unassign each emit audit events for ICS-214 reconstruction.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.fast]


def _login(c: TestClient) -> None:
    r = c.post(
        "/v1/auth/login",
        json={"email": "admin@example.com", "password": "test-pw"},
    )
    assert r.status_code == 200, r.text


def _make_target(c: TestClient) -> dict[str, Any]:
    b = c.post(
        "/v1/boards",
        json={"name": "B", "columns": [{"name": "X", "order": 0}]},
    ).json()
    r = c.post(
        "/v1/capture",
        data={
            "title": "T",
            "lat": "0",
            "lon": "0",
            "board_id": b["id"],
            "column_id": b["columns"][0]["id"],
        },
    )
    return r.json()


def test_get_target_includes_assigned_callsigns_empty(client: TestClient) -> None:
    _login(client)
    t = _make_target(client)
    r = client.get(f"/v1/targets/{t['id']}")
    assert r.status_code == 200
    body = r.json()
    assert body.get("assigned_callsigns") == []


def test_assign_callsign_adds_to_list(client: TestClient) -> None:
    _login(client)
    t = _make_target(client)
    r = client.post(
        f"/v1/targets/{t['id']}/assign",
        json={"callsign": "BISON-01"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "BISON-01" in body["assigned_callsigns"]


def test_assign_duplicate_is_noop(client: TestClient) -> None:
    _login(client)
    t = _make_target(client)
    client.post(f"/v1/targets/{t['id']}/assign", json={"callsign": "BISON-01"})
    r = client.post(f"/v1/targets/{t['id']}/assign", json={"callsign": "BISON-01"})
    assert r.status_code == 200
    body = r.json()
    assert body["assigned_callsigns"].count("BISON-01") == 1


def test_unassign_removes_callsign(client: TestClient) -> None:
    _login(client)
    t = _make_target(client)
    client.post(f"/v1/targets/{t['id']}/assign", json={"callsign": "BISON-01"})
    client.post(f"/v1/targets/{t['id']}/assign", json={"callsign": "WOLF-02"})
    r = client.post(
        f"/v1/targets/{t['id']}/unassign",
        json={"callsign": "BISON-01"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "BISON-01" not in body["assigned_callsigns"]
    assert "WOLF-02" in body["assigned_callsigns"]


def test_assign_requires_auth(client: TestClient) -> None:
    r = client.post(
        "/v1/targets/00000000-0000-0000-0000-000000000000/assign",
        json={"callsign": "X"},
    )
    assert r.status_code == 401
