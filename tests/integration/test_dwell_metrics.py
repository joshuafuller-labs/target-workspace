"""Per-column dwell-time metrics (tw-mwb).

GET /v1/metrics/dwell?board_id=... aggregates from existing audit
events (target.moved + target.created with from/to column ids) to
produce per-column mean / p50 / p95 timing. No DB schema change.

Assumption documented in tw-mwb:
  - Computed on the fly per request. Materialized rollups defer.
  - p50/p95 use sorted-list quantile (no scipy dep).
  - 'Detect-to-destroy' (FIND→FINISH) is presented as the longest
    contiguous time-in-board (created → last seen) — exact column-name
    derivation is workspace-specific so we expose the totals; the SPA
    interprets per its workflow.
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


def test_dwell_returns_shape_for_empty_board(client: TestClient) -> None:
    _login(client)
    board = client.post(
        "/v1/boards",
        json={
            "name": "M",
            "columns": [{"name": "Detect", "order": 0}, {"name": "Finish", "order": 1}],
        },
    ).json()
    r = client.get(f"/v1/metrics/dwell?board_id={board['id']}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "columns" in body
    assert "total_targets" in body
    assert body["total_targets"] == 0


def test_dwell_endpoint_requires_auth(client: TestClient) -> None:
    r = client.get(
        "/v1/metrics/dwell?board_id=00000000-0000-0000-0000-000000000000",
    )
    assert r.status_code == 401


def test_dwell_endpoint_404_for_unknown_board(client: TestClient) -> None:
    _login(client)
    r = client.get(
        "/v1/metrics/dwell?board_id=00000000-0000-0000-0000-000000000000",
    )
    assert r.status_code == 404


def test_dwell_counts_targets_per_column(client: TestClient) -> None:
    _login(client)
    board = client.post(
        "/v1/boards",
        json={
            "name": "M",
            "columns": [{"name": "Detect", "order": 0}, {"name": "Finish", "order": 1}],
        },
    ).json()
    col0 = board["columns"][0]["id"]
    # Spread the lat/lon far enough apart that find_matching_track
    # doesn't merge them into one (correlation tolerance is ~few hundred m).
    for i in range(3):
        client.post(
            "/v1/capture",
            data={
                "title": f"T{i}",
                "lat": str(35.0 + i * 1.0),
                "lon": str(-82.0 - i * 1.0),
                "board_id": board["id"],
                "column_id": col0,
            },
        )
    r = client.get(f"/v1/metrics/dwell?board_id={board['id']}").json()
    assert r["total_targets"] == 3
    cols_by_name = {c["name"]: c for c in r["columns"]}
    assert cols_by_name["Detect"]["current_count"] == 3
    assert cols_by_name["Finish"]["current_count"] == 0
