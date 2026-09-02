"""ICS-211 resource check-in / check-out roster (tw-qkp).

Tracks who's deployed, their certifications, when they checked in/out.

Endpoints:
  POST /v1/resources                  → check in a resource
  GET  /v1/resources                  → current roster (checked-in only)
  POST /v1/resources/{id}/check-out   → mark resource as departed
  GET  /v1/resources/{id}/history     → check-in history

Assumption documented in tw-qkp:
  - Resource is just an entity with callsign + name + certifications.
    No user account required (different mental model from tw-tl9r).
  - Certifications stored as free-form list. Per-cert lookup defers.
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


def test_check_in_creates_resource(client: TestClient) -> None:
    _login(client)
    r = client.post(
        "/v1/resources",
        json={
            "callsign": "BOAT-7",
            "name": "Cajun Navy Boat 7",
            "certifications": ["swift-water-rescue", "first-aid"],
            "location": "Staging Alpha",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["callsign"] == "BOAT-7"
    assert body["status"] == "checked-in"


def test_list_roster_returns_active_only(client: TestClient) -> None:
    _login(client)
    client.post(
        "/v1/resources",
        json={"callsign": "A", "name": "Alpha"},
    )
    b = client.post(
        "/v1/resources",
        json={"callsign": "B", "name": "Bravo"},
    ).json()
    client.post(f"/v1/resources/{b['id']}/check-out")

    r = client.get("/v1/resources").json()
    callsigns = [x["callsign"] for x in r]
    assert "A" in callsigns
    assert "B" not in callsigns


def test_check_out_records_timestamp(client: TestClient) -> None:
    _login(client)
    a = client.post(
        "/v1/resources",
        json={"callsign": "X", "name": "Xena"},
    ).json()
    r = client.post(f"/v1/resources/{a['id']}/check-out")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "checked-out"
    assert body["checked_out_at"] is not None


def test_endpoints_require_auth(client: TestClient) -> None:
    r = client.post("/v1/resources", json={"callsign": "X", "name": "Y"})
    assert r.status_code == 401
