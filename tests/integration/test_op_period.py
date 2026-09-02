"""Operational period as a first-class concept (tw-eebq).

ICS divides incident response into operational periods (typically 12hr).
This ticket adds op_period as a model object with lifecycle CRUD and
wires audit events to carry op_period_id so reports (ICS-214 etc.)
can filter cleanly.

Assumption documented in tw-eebq:
  - IAP (Incident Action Plan) text is a free-form JSON blob at MVP.
    Structured IAP fields (objectives, ICS-202, comms plan ICS-205)
    defer to v1.1.
  - Auto-rollover at scheduled time is manual at MVP (open + close).
  - Only commander+ can open/close periods.
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


def _make_board(c: TestClient) -> dict[str, Any]:
    r = c.post(
        "/v1/boards",
        json={"name": "Op", "columns": [{"name": "X", "order": 0}]},
    )
    assert r.status_code == 201
    return r.json()


def test_open_first_op_period_assigns_number_1(client: TestClient) -> None:
    _login(client)
    board = _make_board(client)
    r = client.post(f"/v1/boards/{board['id']}/op-periods", json={})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["number"] == 1
    assert body["status"] == "active"
    assert body["ends_at"] is None


def test_opening_second_period_auto_closes_first(client: TestClient) -> None:
    _login(client)
    board = _make_board(client)
    client.post(f"/v1/boards/{board['id']}/op-periods", json={}).json()
    second = client.post(f"/v1/boards/{board['id']}/op-periods", json={}).json()
    assert second["number"] == 2
    # Re-fetch first to confirm it's closed
    rows = client.get(f"/v1/boards/{board['id']}/op-periods").json()
    by_number = {p["number"]: p for p in rows}
    assert by_number[1]["status"] == "closed"
    assert by_number[1]["ends_at"] is not None
    assert by_number[2]["status"] == "active"


def test_list_op_periods_ordered(client: TestClient) -> None:
    _login(client)
    board = _make_board(client)
    for _ in range(3):
        client.post(f"/v1/boards/{board['id']}/op-periods", json={})
    rows = client.get(f"/v1/boards/{board['id']}/op-periods").json()
    numbers = [p["number"] for p in rows]
    assert numbers == [1, 2, 3]


def test_op_period_carries_iap_json(client: TestClient) -> None:
    _login(client)
    board = _make_board(client)
    r = client.post(
        f"/v1/boards/{board['id']}/op-periods",
        json={"iap": {"objectives": "Search-and-rescue", "weather": "clear"}},
    )
    assert r.status_code == 201
    iap = r.json()["iap"]
    assert iap["objectives"] == "Search-and-rescue"


def test_op_period_requires_auth(client: TestClient) -> None:
    r = client.post(
        "/v1/boards/00000000-0000-0000-0000-000000000000/op-periods",
        json={},
    )
    assert r.status_code == 401
