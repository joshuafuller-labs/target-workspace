"""Column add/edit/delete on existing boards (tw-itn).

During an incident the operational picture changes — a Transport
Coordination column emerges, or two columns merge. The board needs
column CRUD without rebuilding the whole board.

Assumption documented in tw-itn:
  - DELETE refuses (409) if any targets remain in the column. Caller
    must move them first.
  - Column reorder is supported via PATCH .order — full reorder
    transactions across multiple columns are a follow-up.
  - commander+ required (boards are workspace-shared state).
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.fast]


def _login_admin(c: TestClient) -> None:
    r = c.post(
        "/v1/auth/login",
        json={"email": "admin@example.com", "password": "test-pw"},
    )
    assert r.status_code == 200, r.text


def _make_board(c: TestClient) -> dict[str, Any]:
    r = c.post(
        "/v1/boards",
        json={
            "name": "Live",
            "columns": [{"name": "Intake", "order": 0}, {"name": "Active", "order": 1}],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_add_column_appends_to_board(client: TestClient) -> None:
    _login_admin(client)
    board = _make_board(client)
    r = client.post(
        f"/v1/boards/{board['id']}/columns",
        json={"name": "Transport", "order": 2, "requires_approval": False},
    )
    assert r.status_code == 201, r.text
    refreshed = client.get(f"/v1/boards/{board['id']}").json()
    names = [c["name"] for c in refreshed["columns"]]
    assert "Transport" in names


def test_patch_column_renames(client: TestClient) -> None:
    _login_admin(client)
    board = _make_board(client)
    column_id = board["columns"][0]["id"]
    r = client.patch(
        f"/v1/boards/{board['id']}/columns/{column_id}",
        json={"name": "Renamed"},
    )
    assert r.status_code == 200, r.text
    refreshed = client.get(f"/v1/boards/{board['id']}").json()
    assert refreshed["columns"][0]["name"] == "Renamed"


def test_delete_empty_column_succeeds(client: TestClient) -> None:
    _login_admin(client)
    board = _make_board(client)
    # Add a third empty column we can safely delete
    r = client.post(
        f"/v1/boards/{board['id']}/columns",
        json={"name": "Disposable", "order": 5},
    )
    new_col = r.json()
    r = client.delete(f"/v1/boards/{board['id']}/columns/{new_col['id']}")
    assert r.status_code == 204, r.text
    refreshed = client.get(f"/v1/boards/{board['id']}").json()
    names = [c["name"] for c in refreshed["columns"]]
    assert "Disposable" not in names


def test_delete_column_with_target_returns_409(client: TestClient) -> None:
    _login_admin(client)
    board = _make_board(client)
    column_id = board["columns"][0]["id"]
    # Put a target in the column
    client.post(
        "/v1/capture",
        data={
            "title": "Stuck",
            "lat": "0",
            "lon": "0",
            "board_id": board["id"],
            "column_id": column_id,
        },
    )
    r = client.delete(f"/v1/boards/{board['id']}/columns/{column_id}")
    assert r.status_code == 409, r.text


def test_column_crud_admin_only(client: TestClient) -> None:
    r = client.post(
        "/v1/boards/00000000-0000-0000-0000-000000000000/columns",
        json={"name": "X", "order": 0},
    )
    assert r.status_code == 401
