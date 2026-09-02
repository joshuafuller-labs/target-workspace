"""Geofence engine — arrival/departure detection (tw-a6kg).

For each PLI upsert, evaluate whether the callsign is inside the
geofence of any target it's assigned to. State transitions emit
'presence.arrived' / 'presence.departed' events on the workspace
realtime broker.

Default radius: max(target.ce, 100m). Per-card override is a follow-up.

Assumption documented in tw-a6kg:
  - Engine runs synchronously inside upsert_pli (cheap). No background
    sweep needed at MVP — geofence is evaluated only when a position
    update arrives.
  - Hysteresis (N consecutive insides) defers to v1.x. MVP: first inside
    fires arrived, first outside (after a prior inside) fires departed.
  - 'on-station' (arrived + still inside after T seconds) is a separate
    timer-driven concern; deferred.
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


def _make_target(c: TestClient, callsign: str) -> dict[str, Any]:
    board = c.post(
        "/v1/boards",
        json={"name": "B", "columns": [{"name": "X", "order": 0}]},
    ).json()
    t = c.post(
        "/v1/capture",
        data={
            "title": "T",
            "lat": "35.60000",
            "lon": "-82.55000",
            "board_id": board["id"],
            "column_id": board["columns"][0]["id"],
        },
    ).json()
    c.post(f"/v1/targets/{t['id']}/assign", json={"callsign": callsign})
    return t


def test_callsign_inside_target_radius_is_arrived(client: TestClient) -> None:
    from target_workspace.api.geofence import evaluate_geofence

    _login(client)
    t = _make_target(client, "BISON-01")

    # PLI very close to the target → inside default radius.
    transitions = evaluate_geofence(
        target_id=t["id"],
        target_lat=35.60000,
        target_lon=-82.55000,
        target_ce=None,
        callsign="BISON-01",
        pli_lat=35.60001,  # ~1m away
        pli_lon=-82.55000,
    )
    assert any(
        t["event"] == "presence.arrived" and t["callsign"] == "BISON-01" for t in transitions
    )


def test_callsign_outside_after_arrived_is_departed(client: TestClient) -> None:
    from target_workspace.api.geofence import evaluate_geofence

    _login(client)
    t = _make_target(client, "BISON-01")

    # First: inside (arrived)
    evaluate_geofence(
        target_id=t["id"],
        target_lat=35.60000,
        target_lon=-82.55000,
        target_ce=None,
        callsign="BISON-01",
        pli_lat=35.60001,
        pli_lon=-82.55000,
    )
    # Then: far outside
    transitions = evaluate_geofence(
        target_id=t["id"],
        target_lat=35.60000,
        target_lon=-82.55000,
        target_ce=None,
        callsign="BISON-01",
        pli_lat=35.70000,  # ~11km away
        pli_lon=-82.55000,
    )
    assert any(
        t["event"] == "presence.departed" and t["callsign"] == "BISON-01" for t in transitions
    )


def test_no_transition_for_persistent_inside(client: TestClient) -> None:
    """Once arrived, subsequent inside updates don't re-emit arrived."""
    from target_workspace.api.geofence import evaluate_geofence

    _login(client)
    t = _make_target(client, "BISON-01")
    args = {
        "target_id": t["id"],
        "target_lat": 35.60000,
        "target_lon": -82.55000,
        "target_ce": None,
        "callsign": "BISON-01",
        "pli_lat": 35.60001,
        "pli_lon": -82.55000,
    }
    first = evaluate_geofence(**args)
    second = evaluate_geofence(**args)
    assert any(t["event"] == "presence.arrived" for t in first)
    assert second == [], f"expected no events on persistent inside, got {second}"


def test_default_radius_uses_target_ce_when_present(client: TestClient) -> None:
    """If target.ce is set, default radius = max(ce, 100m)."""
    from target_workspace.api.geofence import default_radius_m

    assert default_radius_m(ce=50.0) == 100.0  # min 100m
    assert default_radius_m(ce=500.0) == 500.0
    assert default_radius_m(ce=None) == 100.0
