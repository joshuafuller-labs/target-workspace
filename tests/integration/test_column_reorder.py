"""Atomic column reorder (tw-65l).

Per-column PATCH (from tw-itn) lets you change one column's order, but
multi-column reorder needs atomic application — otherwise the board
spends a transient interval with two columns sharing an order value.

Endpoint:
  POST /v1/boards/{id}/columns/reorder
  Body: { columns: [{id, order}, ...] }
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
    return c.post(
        "/v1/boards",
        json={
            "name": "R",
            "columns": [
                {"name": "A", "order": 0},
                {"name": "B", "order": 1},
                {"name": "C", "order": 2},
            ],
        },
    ).json()


def test_atomic_reorder_applies(client: TestClient) -> None:
    _login(client)
    b = _make_board(client)
    a, c_b, c = b["columns"]
    # New order: C, B, A
    r = client.post(
        f"/v1/boards/{b['id']}/columns/reorder",
        json={
            "columns": [
                {"id": a["id"], "order": 2},
                {"id": c_b["id"], "order": 1},
                {"id": c["id"], "order": 0},
            ],
        },
    )
    assert r.status_code == 200, r.text

    refreshed = client.get(f"/v1/boards/{b['id']}").json()
    cols_by_order = sorted(refreshed["columns"], key=lambda x: x["order"])
    assert [c["name"] for c in cols_by_order] == ["C", "B", "A"]


def test_reorder_with_unknown_column_404(client: TestClient) -> None:
    _login(client)
    b = _make_board(client)
    r = client.post(
        f"/v1/boards/{b['id']}/columns/reorder",
        json={
            "columns": [
                {"id": "00000000-0000-0000-0000-000000000000", "order": 0},
            ],
        },
    )
    assert r.status_code == 404, r.text


def test_reorder_requires_auth(client: TestClient) -> None:
    r = client.post(
        "/v1/boards/00000000-0000-0000-0000-000000000000/columns/reorder",
        json={"columns": []},
    )
    assert r.status_code == 401
