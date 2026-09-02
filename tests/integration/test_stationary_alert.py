"""Stationary-too-long safety alert (tw-zba3).

If a callsign assigned to a target hasn't moved more than N meters in
T minutes, flag it as 'stationary alert'. Per-callsign state lives in
the PLI presence cache; the check function evaluates from cache history.

Assumption documented in tw-zba3:
  - At MVP we ship a check function (api/safety.is_stationary) that
    callers can hit on demand. A timer-driven background sweep is
    a v1.x follow-up.
  - Defaults: 5 minutes, 25-meter movement floor.
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


def test_callsign_with_no_history_is_not_stationary() -> None:
    from target_workspace.api.safety import is_stationary

    res = is_stationary(callsign="GHOST-01", min_minutes=5.0, max_drift_m=25.0)
    assert res is False


def test_callsign_recently_moved_is_not_stationary() -> None:
    from target_workspace.api.presence import upsert_pli
    from target_workspace.api.safety import is_stationary

    upsert_pli(
        callsign="MOVER-01",
        lat=35.6,
        lon=-82.55,
        hae=None,
        time_iso="2026-05-18T10:00:00Z",
        speed=5.0,
        source="cot-in",
    )
    # Fresh entry — under min_minutes elapsed
    assert is_stationary(callsign="MOVER-01", min_minutes=5.0, max_drift_m=25.0) is False


def test_callsign_stationary_long_enough_is_stationary() -> None:
    from target_workspace.api.presence import upsert_pli
    from target_workspace.api.safety import is_stationary

    # Use min_minutes=0 to bypass the elapsed-time floor for the test —
    # any entry with speed=0 is stationary by the speed rule.
    upsert_pli(
        callsign="STATIC-01",
        lat=35.6,
        lon=-82.55,
        hae=None,
        time_iso="2026-05-18T10:00:00Z",
        speed=0.0,
        source="cot-in",
    )
    assert is_stationary(callsign="STATIC-01", min_minutes=0.0, max_drift_m=25.0) is True


def test_endpoint_returns_alert_callsigns(client: TestClient) -> None:
    """GET /v1/safety/stationary — returns callsigns currently flagged."""
    from target_workspace.api.presence import upsert_pli

    _login(client)
    upsert_pli(
        callsign="STATIC-09",
        lat=35.6,
        lon=-82.55,
        hae=None,
        time_iso="2026-05-18T10:00:00Z",
        speed=0.0,
        source="cot-in",
    )
    # min_minutes=0 in the query so the test doesn't depend on wall time
    r = client.get("/v1/safety/stationary?min_minutes=0")
    assert r.status_code == 200, r.text
    callsigns = [row["callsign"] for row in r.json()]
    assert "STATIC-09" in callsigns
