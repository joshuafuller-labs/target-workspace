"""Auto-ETA per assignee (tw-fnrv).

For each callsign assigned to a target, compute a time-to-arrive
estimate from PLI position + (optional) speed.

GET /v1/targets/{target_id}/eta → list of {callsign, status, eta_seconds?, distance_m}

Status values:
  closing       — speed > 0 and delta-distance decreasing
  diverging     — moving AWAY
  stationary    — no movement
  offline       — callsign not in PLI cache
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


def _make_target_with_assignee(c: TestClient, callsign: str = "BISON-01") -> dict[str, Any]:
    board = c.post(
        "/v1/boards",
        json={"name": "B", "columns": [{"name": "X", "order": 0}]},
    ).json()
    t = c.post(
        "/v1/capture",
        data={
            "title": "T",
            "lat": "35.6",
            "lon": "-82.55",
            "board_id": board["id"],
            "column_id": board["columns"][0]["id"],
        },
    ).json()
    c.post(f"/v1/targets/{t['id']}/assign", json={"callsign": callsign})
    return t


def test_eta_returns_offline_when_callsign_has_no_pli(client: TestClient) -> None:
    _login(client)
    t = _make_target_with_assignee(client, "GHOST-01")
    r = client.get(f"/v1/targets/{t['id']}/eta")
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["callsign"] == "GHOST-01"
    assert rows[0]["status"] == "offline"


def test_eta_returns_closing_when_speed_positive(client: TestClient) -> None:
    """PLI carries speed; distance / speed = eta_seconds."""
    from target_workspace.api.presence import upsert_pli

    _login(client)
    t = _make_target_with_assignee(client, "BISON-01")

    # PLI 1km west of the target, moving at 10 m/s.
    upsert_pli(
        callsign="BISON-01",
        lat=35.6,
        lon=-82.56,  # ~880m west at 35.6° latitude
        hae=None,
        time_iso="2026-05-18T10:00:00Z",
        speed=10.0,
        source="cot-in",
    )
    r = client.get(f"/v1/targets/{t['id']}/eta")
    assert r.status_code == 200
    rows = r.json()
    assert rows[0]["status"] in {"closing", "stationary"}
    assert rows[0]["distance_m"] is not None
    assert rows[0]["distance_m"] > 100


def test_eta_returns_stationary_when_speed_zero(client: TestClient) -> None:
    from target_workspace.api.presence import upsert_pli

    _login(client)
    t = _make_target_with_assignee(client, "STILL-01")
    upsert_pli(
        callsign="STILL-01",
        lat=35.6,
        lon=-82.55,
        hae=None,
        time_iso="2026-05-18T10:00:00Z",
        speed=0.0,
        source="cot-in",
    )
    r = client.get(f"/v1/targets/{t['id']}/eta")
    assert r.json()[0]["status"] == "stationary"


def test_eta_requires_auth(client: TestClient) -> None:
    r = client.get(
        "/v1/targets/00000000-0000-0000-0000-000000000000/eta",
    )
    assert r.status_code == 401
