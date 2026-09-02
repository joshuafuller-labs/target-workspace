"""Bulk target import — paste-a-list / CSV (tw-j3x6).

POST /v1/targets/bulk
  Body: {
    board_id: UUID,
    column_id: UUID,
    rows: [
      { name: str, lat: float, lon: float, remarks: str | None,
        cot_type: str | None }, ...
    ],
  }
  → 201 with {
    rows: [
      { ok: true, id: UUID, name: str } |
      { ok: false, error: str, input: {...} }
    ]
  }

MVP: no geocoding, no idempotency-per-row. The audit-event aggregate
('bulk_imported' referencing all created ids) lives in a separate
ticket so this stays focused.
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
        json={"name": "B", "columns": [{"name": "Reported", "order": 0}]},
    )
    assert r.status_code in (200, 201)
    return r.json()


def test_bulk_creates_all_rows(client: TestClient) -> None:
    _login(client)
    b = _make_board(client)
    rows = [
        {"name": "addr-1", "lat": 35.6, "lon": -82.55},
        {"name": "addr-2", "lat": 35.7, "lon": -82.5},
        {"name": "addr-3", "lat": 35.8, "lon": -82.45},
    ]
    r = client.post(
        "/v1/targets/bulk",
        json={
            "board_id": b["id"],
            "column_id": b["columns"][0]["id"],
            "rows": rows,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert len(body["rows"]) == 3
    for row in body["rows"]:
        assert row["ok"] is True
        assert "id" in row


def test_bulk_reports_per_row_errors(client: TestClient) -> None:
    _login(client)
    b = _make_board(client)
    rows = [
        {"name": "ok", "lat": 35.6, "lon": -82.55},
        {"name": "bad-lat", "lat": 999.0, "lon": -82.55},
        {"name": "missing-name", "lat": 35.7, "lon": -82.55},
    ]
    rows[2]["name"] = ""  # invalidate name
    r = client.post(
        "/v1/targets/bulk",
        json={
            "board_id": b["id"],
            "column_id": b["columns"][0]["id"],
            "rows": rows,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert len(body["rows"]) == 3
    assert body["rows"][0]["ok"] is True
    assert body["rows"][1]["ok"] is False
    assert body["rows"][2]["ok"] is False
    assert "error" in body["rows"][1]
    assert "error" in body["rows"][2]


def test_bulk_validates_board_id(client: TestClient) -> None:
    _login(client)
    r = client.post(
        "/v1/targets/bulk",
        json={
            "board_id": "00000000-0000-0000-0000-000000000000",
            "column_id": "00000000-0000-0000-0000-000000000000",
            "rows": [{"name": "x", "lat": 0.0, "lon": 0.0}],
        },
    )
    assert r.status_code == 404


def test_bulk_requires_auth(client: TestClient) -> None:
    r = client.post(
        "/v1/targets/bulk",
        json={
            "board_id": "00000000-0000-0000-0000-000000000000",
            "column_id": "00000000-0000-0000-0000-000000000000",
            "rows": [],
        },
    )
    assert r.status_code == 401


def test_bulk_rejects_empty_rows(client: TestClient) -> None:
    _login(client)
    b = _make_board(client)
    r = client.post(
        "/v1/targets/bulk",
        json={
            "board_id": b["id"],
            "column_id": b["columns"][0]["id"],
            "rows": [],
        },
    )
    assert r.status_code == 422


def test_bulk_caps_row_count(client: TestClient) -> None:
    """A guardrail — runaway bulk import shouldn't take down the box."""
    _login(client)
    b = _make_board(client)
    rows = [{"name": f"r-{i}", "lat": 35.0 + i * 0.001, "lon": -82.0} for i in range(2000)]
    r = client.post(
        "/v1/targets/bulk",
        json={
            "board_id": b["id"],
            "column_id": b["columns"][0]["id"],
            "rows": rows,
        },
    )
    assert r.status_code == 422
