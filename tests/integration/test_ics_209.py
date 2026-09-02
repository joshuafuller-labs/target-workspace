"""ICS-209 Incident Status Summary export (tw-5hq).

tw-vem9 already shipped ICS-214 (Activity Log). This extends the
forms router with ICS-209 (Incident Status Summary) — board state
roll-up at a point in time.

ICS-204 (Assignment List from tasks+resources) requires the
entity_kind work in tw-auf and resource roster in tw-qkp; defers.

Assumption documented in tw-5hq:
  - ICS-209 markdown only at MVP (matches the tw-vem9 ICS-214 pattern).
  - Filter by op_period_id optional; defaults to the most recent
    active period on the board (tw-eebq).
  - The 'incident status' is derived from current target counts per
    column + recent activity counts.
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


def _make_board_with_targets(c: TestClient, n: int = 3) -> dict[str, Any]:
    b = c.post(
        "/v1/boards",
        json={
            "name": "Incident-Status",
            "columns": [
                {"name": "Detect", "order": 0},
                {"name": "Active", "order": 1},
            ],
        },
    ).json()
    col = b["columns"][0]["id"]
    for i in range(n):
        c.post(
            "/v1/capture",
            data={
                "title": f"Subject-{i}",
                "lat": str(35.0 + i * 0.01),
                "lon": str(-82.5 - i * 0.01),
                "board_id": b["id"],
                "column_id": col,
            },
        )
    return b


def test_ics209_returns_markdown_with_column_counts(client: TestClient) -> None:
    _login(client)
    board = _make_board_with_targets(client, n=3)
    r = client.get(f"/v1/boards/{board['id']}/forms/ics-209")
    assert r.status_code == 200, r.text
    assert "text/markdown" in r.headers.get("content-type", "")
    body = r.text
    assert "ICS-209" in body
    assert "Incident Status Summary" in body
    assert "Incident-Status" in body
    # Counts per column
    assert "Detect" in body
    assert "Active" in body
    # The 3 captured targets land in Detect
    assert "3" in body


def test_ics209_requires_auth(client: TestClient) -> None:
    r = client.get(
        "/v1/boards/00000000-0000-0000-0000-000000000000/forms/ics-209",
    )
    assert r.status_code == 401


def test_ics209_404_for_unknown_board(client: TestClient) -> None:
    _login(client)
    r = client.get(
        "/v1/boards/00000000-0000-0000-0000-000000000000/forms/ics-209",
    )
    assert r.status_code == 404
