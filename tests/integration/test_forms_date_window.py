"""Date-window + detail-row branch coverage for ICS form exports.

The existing test_ics214_export / test_ics_209 cover the happy path, auth,
and 404, but not: start_iso/end_iso filtering, invalid-ISO 422s, the
operational-period header line, or the ICS-214 detail-column rendering
(from/to/justification) that only appears when a target.moved audit row
exists. This file fills those branches in forms.py.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.fast]

_MISSING_ID = "00000000-0000-0000-0000-000000000000"


def _login(c: TestClient) -> None:
    r = c.post("/v1/auth/login", json={"email": "admin@example.com", "password": "test-pw"})
    assert r.status_code == 200, r.text


def _make_board(c: TestClient) -> dict[str, Any]:
    r = c.post(
        "/v1/boards",
        json={
            "name": "Ops",
            "columns": [{"name": "Active", "order": 0}, {"name": "Done", "order": 1}],
        },
    )
    assert r.status_code == 201, r.text
    out: dict[str, Any] = r.json()
    return out


def _make_target_and_move(c: TestClient, board: dict[str, Any]) -> None:
    """Create a target and move it so a target.moved audit row exists
    (with from/to column ids + justification → ICS-214 detail columns)."""
    active, done = board["columns"][0]["id"], board["columns"][1]["id"]
    created = c.post(
        "/v1/capture",
        data={
            "title": "COBRA-12",
            "lat": "35.6",
            "lon": "-82.55",
            "board_id": board["id"],
            "column_id": active,
        },
    ).json()
    r = c.post(
        f"/v1/targets/{created['id']}/move",
        json={"column_id": done, "justification": "cross-cue confirmed"},
    )
    assert r.status_code == 200, r.text


# ── ICS-214 date window + detail rows ───────────────────────────────────


def test_ics214_with_date_window(client: TestClient) -> None:
    _login(client)
    board = _make_board(client)
    _make_target_and_move(client, board)

    r = client.get(
        f"/v1/boards/{board['id']}/forms/ics-214",
        params={"start_iso": "2000-01-01T00:00:00Z", "end_iso": "2100-01-01T00:00:00Z"},
    )
    assert r.status_code == 200, r.text
    body = r.text
    assert "Operational period:" in body
    # The move audit row renders from=/to=/reason= detail columns.
    assert "to=" in body
    assert "reason=cross-cue confirmed" in body


def test_ics214_invalid_start_iso_422(client: TestClient) -> None:
    _login(client)
    board = _make_board(client)
    r = client.get(
        f"/v1/boards/{board['id']}/forms/ics-214",
        params={"start_iso": "not-a-date"},
    )
    assert r.status_code == 422
    assert "invalid start_iso" in r.json()["detail"]


def test_ics214_invalid_end_iso_422(client: TestClient) -> None:
    _login(client)
    board = _make_board(client)
    r = client.get(
        f"/v1/boards/{board['id']}/forms/ics-214",
        params={"end_iso": "13:99 nonsense"},
    )
    assert r.status_code == 422
    assert "invalid end_iso" in r.json()["detail"]


# ── ICS-209 date window + invalid ISO ───────────────────────────────────


def test_ics209_with_date_window_sets_period_label(client: TestClient) -> None:
    _login(client)
    board = _make_board(client)
    _make_target_and_move(client, board)

    r = client.get(
        f"/v1/boards/{board['id']}/forms/ics-209",
        params={"start_iso": "2000-01-01T00:00:00Z", "end_iso": "2100-01-01T00:00:00Z"},
    )
    assert r.status_code == 200, r.text
    body = r.text
    assert "Operational period:" in body
    assert "2000-01-01" in body


def test_ics209_start_only_period_label_open_end(client: TestClient) -> None:
    _login(client)
    board = _make_board(client)
    r = client.get(
        f"/v1/boards/{board['id']}/forms/ics-209",
        params={"start_iso": "2000-01-01T00:00:00Z"},
    )
    assert r.status_code == 200, r.text
    assert "→ open" in r.text


def test_ics209_invalid_start_iso_422(client: TestClient) -> None:
    _login(client)
    board = _make_board(client)
    r = client.get(
        f"/v1/boards/{board['id']}/forms/ics-209",
        params={"start_iso": "garbage"},
    )
    assert r.status_code == 422
    assert "invalid start_iso" in r.json()["detail"]


def test_ics209_invalid_end_iso_422(client: TestClient) -> None:
    _login(client)
    board = _make_board(client)
    r = client.get(
        f"/v1/boards/{board['id']}/forms/ics-209",
        params={"end_iso": "garbage"},
    )
    assert r.status_code == 422
    assert "invalid end_iso" in r.json()["detail"]
