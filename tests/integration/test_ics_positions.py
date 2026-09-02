"""ICS-position-based authority (tw-l40z).

ICS organizes authority by POSITION, not by user. The IC has authority
until they transfer it. Position assignments are time-windowed and
form a chain of custody.

MVP scope per the ticket:
  - position table with seeded ICS positions
  - position_assignment table with chain of custody
  - assign / current / history endpoints
  - audit events on assign / transfer / vacate

Assumption documented in tw-l40z:
  - Approval gate extension (require position-holder sign-off) is a
    follow-up — needs to wire into the existing workflow.transition_target.
  - Position-conferring badges in TargetDetail UI defer to v1.1.
  - Unified Command (multiple ICs concurrently) blocks on tw-eo6l —
    that decision shipped ADR 0015 (groups-in-workspace) so multi-org
    IC is a future feature on this primitive.
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


def test_default_ics_positions_seeded(client: TestClient) -> None:
    _login(client)
    r = client.get("/v1/positions")
    assert r.status_code == 200
    rows = r.json()
    codes = {p["ics_code"] for p in rows}
    # Standard ICS positions
    expected = {"IC", "OSC", "PSC", "LSC", "FSC", "SAFETY", "PIO", "LIAISON"}
    assert expected.issubset(codes), f"missing positions: {expected - codes}"


def test_assign_user_to_position(client: TestClient) -> None:
    _login(client)
    pos = client.get("/v1/positions").json()
    osc = next(p for p in pos if p["ics_code"] == "OSC")
    me = client.get("/v1/auth/me").json()

    r = client.post(
        f"/v1/positions/{osc['id']}/assignments",
        json={"user_id": me["id"]},
    )
    assert r.status_code == 201, r.text

    current = client.get("/v1/positions/current").json()
    osc_current = next(p for p in current if p["ics_code"] == "OSC")
    assert osc_current["assignment"]["user_id"] == me["id"]


def test_assign_transfers_close_prior_assignment(client: TestClient) -> None:
    """Assigning a new holder auto-closes the prior active assignment."""
    _login(client)
    pos = client.get("/v1/positions").json()
    ic_id = next(p["id"] for p in pos if p["ics_code"] == "IC")
    admin = client.get("/v1/auth/me").json()
    deputy = client.post(
        "/v1/users",
        json={
            "email": "deputy@example.com",
            "display_name": "Deputy",
            "role": "commander",
            "password": "test-pass",
        },
    ).json()

    # Admin takes IC, then transfers to Deputy
    client.post(f"/v1/positions/{ic_id}/assignments", json={"user_id": admin["id"]})
    client.post(f"/v1/positions/{ic_id}/assignments", json={"user_id": deputy["id"]})

    history = client.get(f"/v1/positions/{ic_id}/history").json()
    assert len(history) == 2
    # First (admin) is closed; second (deputy) is open
    assigns_by_user = {h["user_id"]: h for h in history}
    assert assigns_by_user[admin["id"]]["ends_at"] is not None
    assert assigns_by_user[deputy["id"]]["ends_at"] is None
    # Chain of custody
    assert (
        assigns_by_user[deputy["id"]]["transferred_from_assignment_id"]
        == (assigns_by_user[admin["id"]]["id"])
    )


def test_assignment_emits_audit_event(client: TestClient) -> None:
    _login(client)
    pos = client.get("/v1/positions").json()
    ic = next(p for p in pos if p["ics_code"] == "IC")
    me = client.get("/v1/auth/me").json()
    client.post(f"/v1/positions/{ic['id']}/assignments", json={"user_id": me["id"]})

    events = client.get("/v1/audit?limit=200").json()
    types = {e["event_type"] for e in events}
    assert "position.assigned" in types


def test_position_endpoints_require_auth(client: TestClient) -> None:
    r = client.get("/v1/positions")
    assert r.status_code == 401
