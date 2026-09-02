"""Dwell-computation branch coverage for /v1/metrics/dwell (tw-mwb).

test_dwell_metrics covers the empty/auth/404/count cases but never moves a
target between columns, so the per-(target, column) span computation
(audit-event walk, dwell accumulation, mean/p50/p95) is uncovered. This
file creates a target and moves it so audit rows exist, then asserts the
dwell aggregation runs and produces a positive duration.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, col, select

from target_workspace.db import get_engine
from target_workspace.db.tables import AuditEventTable

pytestmark = [pytest.mark.fast]


def _login(c: TestClient) -> None:
    r = c.post("/v1/auth/login", json={"email": "admin@example.com", "password": "test-pw"})
    assert r.status_code == 200, r.text


def _make_board(c: TestClient) -> dict[str, Any]:
    r = c.post(
        "/v1/boards",
        json={
            "name": "F3EAD",
            "columns": [
                {"name": "FIND", "order": 0},
                {"name": "FIX", "order": 1},
                {"name": "FINISH", "order": 2},
            ],
        },
    )
    assert r.status_code == 201, r.text
    out: dict[str, Any] = r.json()
    return out


def _set_move_times(target_id: str, *occurred_at: datetime) -> None:
    with Session(get_engine()) as session:
        rows = session.exec(
            select(AuditEventTable)
            .where(AuditEventTable.target_id == UUID(target_id))
            .where(col(AuditEventTable.event_type).in_(["target.moved", "transitioned"]))
            .order_by(col(AuditEventTable.occurred_at).asc()),
        ).all()
        assert len(rows) == len(occurred_at)
        for row, timestamp in zip(rows, occurred_at, strict=True):
            row.occurred_at = timestamp
            session.add(row)
        session.commit()


def test_dwell_computes_spans_after_moves(client: TestClient) -> None:
    _login(client)
    board = _make_board(client)
    find_col, fix_col, finish_col = (c["id"] for c in board["columns"])

    created = client.post(
        "/v1/capture",
        data={
            "title": "COBRA-12",
            "lat": "35.6",
            "lon": "-82.55",
            "board_id": board["id"],
            "column_id": find_col,
        },
    ).json()
    tid = created["id"]

    assert client.post(f"/v1/targets/{tid}/move", json={"column_id": fix_col}).status_code == 200
    assert client.post(f"/v1/targets/{tid}/move", json={"column_id": finish_col}).status_code == 200
    base = datetime(2026, 6, 5, 12, 0, 0)
    _set_move_times(tid, base, base + timedelta(seconds=5))

    r = client.get(f"/v1/metrics/dwell?board_id={board['id']}")
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["total_targets"] == 1
    assert body["total_audit_events"] >= 2

    cols_by_name = {c["name"]: c for c in body["columns"]}
    # The card ended in FINISH, so that's where the current_count lands.
    assert cols_by_name["FINISH"]["current_count"] == 1

    # At least one column accumulated a measured dwell span with stats.
    counted = [c for c in body["columns"] if c["dwell_seconds"]["count"] > 0]
    assert counted, body["columns"]
    sample = counted[0]["dwell_seconds"]
    assert sample["mean"] is not None
    assert sample["p50"] is not None
    assert sample["p95"] is not None
    assert sample["mean"] >= 0.0


def test_dwell_quantile_with_multiple_spans(client: TestClient) -> None:
    """Multiple dwell samples in one column exercise the >1-element
    quantile interpolation branch of _quantile (not just the len==1 case).

    A column only accumulates a dwell span when there's an audit event
    that moves a target INTO it (sets to_column_id) followed by another
    event. The initial capture has no to_column_id, so the FIX column —
    entered by the first move, exited by the second — is where samples
    land. Three targets each doing FIND->FIX->FINISH gives FIX three
    samples → interpolated p50/p95.
    """
    _login(client)
    board = _make_board(client)
    find_col, fix_col, finish_col = (c["id"] for c in board["columns"])

    for i in range(3):
        created = client.post(
            "/v1/capture",
            data={
                "title": f"T{i}",
                "lat": str(35.0 + i),
                "lon": str(-82.0 - i),
                "board_id": board["id"],
                "column_id": find_col,
            },
        ).json()
        tid = created["id"]
        client.post(f"/v1/targets/{tid}/move", json={"column_id": fix_col})
        client.post(f"/v1/targets/{tid}/move", json={"column_id": finish_col})
        base = datetime(2026, 6, 5, 12, 0, i)
        _set_move_times(tid, base, base + timedelta(seconds=i + 1))

    r = client.get(f"/v1/metrics/dwell?board_id={board['id']}").json()
    fix_stats = next(c for c in r["columns"] if c["name"] == "FIX")["dwell_seconds"]
    assert fix_stats["count"] == 3
    assert fix_stats["p50"] is not None
    assert fix_stats["p95"] is not None
    # FIND never has a move INTO it (capture sets no to_column_id), so its
    # dwell bucket stays empty (None stats) — the empty-bucket branch.
    find_stats = next(c for c in r["columns"] if c["name"] == "FIND")["dwell_seconds"]
    assert find_stats["count"] == 0
    assert find_stats["mean"] is None
