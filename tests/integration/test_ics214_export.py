"""ICS-214 Activity Log export (tw-vem9).

Audit-log-to-text generator. The cheapest ICS win available — audit
data is already there; this is templated output on top.

Assumption documented in tw-vem9:
  - MVP ships markdown / text output ONLY. PDF generation needs an
    extra dependency (weasyprint) not currently in the deps; deferred
    to v1.1 as a single-line addition once weasyprint is added.
  - Op-period filtering uses query-string start_iso / end_iso since
    tw-eebq (first-class op_period table) is post-MVP per ADR 0014.
    Without dates the form returns events for the whole board.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.fast]


def _login_admin(c: TestClient) -> None:
    r = c.post("/v1/auth/login", json={"email": "admin@example.com", "password": "test-pw"})
    assert r.status_code == 200, r.text


def _make_board(c: TestClient) -> str:
    r = c.post(
        "/v1/boards",
        json={
            "name": "Ops",
            "columns": [{"name": "Active", "order": 0}, {"name": "Done", "order": 1}],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_ics214_returns_markdown_for_a_board(client: TestClient) -> None:
    _login_admin(client)
    board_id = _make_board(client)
    # Create a couple of targets so there are audit events
    cols = client.get(f"/v1/boards/{board_id}").json()["columns"]
    col_id = cols[0]["id"]
    for i in range(2):
        client.post(
            "/v1/capture",
            data={
                "title": f"Event {i}",
                "lat": "35.6",
                "lon": "-82.5",
                "board_id": board_id,
                "column_id": col_id,
            },
        )

    r = client.get(f"/v1/boards/{board_id}/forms/ics-214")
    assert r.status_code == 200, r.text
    assert "text/markdown" in r.headers.get("content-type", "")
    body = r.text
    # Form heading + workspace context
    assert "ICS-214" in body
    assert "Activity Log" in body
    assert "Ops" in body
    # At least one auth audit event present (the admin login that set
    # up this test wrote auth.login.success). target.created audit
    # emission is a separate follow-up — currently create_target only
    # publishes to the realtime broker, not the audit log.
    assert "auth.login.success" in body


def test_ics214_requires_auth(client: TestClient) -> None:
    r = client.get("/v1/boards/00000000-0000-0000-0000-000000000000/forms/ics-214")
    assert r.status_code == 401


def test_ics214_404_for_unknown_board(client: TestClient) -> None:
    _login_admin(client)
    r = client.get("/v1/boards/00000000-0000-0000-0000-000000000000/forms/ics-214")
    assert r.status_code == 404
