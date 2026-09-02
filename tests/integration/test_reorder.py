"""Reorder targets within a column (tw-owu).

Float-position scheme — drag-reorder inserts at the midpoint between
adjacent rows so no other rows have to move. These tests cover:

- Top-of-column placement (after_id=None).
- Mid-column placement (midpoint maintained).
- Bottom-of-column placement (anchor.position + 1.0).
- Cross-column reorder.
- 404 paths (target / anchor not found in column).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(name="client")
def authenticated_reorder_client(authenticated_client: TestClient) -> TestClient:
    return authenticated_client


def _make_board(client: TestClient) -> tuple[str, str]:
    r = client.post(
        "/v1/boards",
        json={
            "name": "T",
            "columns": [{"name": "Find", "order": 0}, {"name": "Fix", "order": 1}],
        },
    )
    assert r.status_code == 201, r.text
    board = r.json()
    return board["id"], board["columns"][0]["id"]


_NAME_INDEX: dict[str, int] = {}


def _make_target(client: TestClient, board_id: str, column_id: str, name: str) -> str:
    # Track correlation merges fixes within 500m + 30min of the same
    # contact — push each test target onto its own coordinate so we
    # measurably have distinct rows to reorder.
    idx = _NAME_INDEX.setdefault(name, ord(name[0]) - 65)
    r = client.post(
        "/v1/targets",
        json={
            "board_id": board_id,
            "column_id": column_id,
            "name": name,
            "lat": 33.0 + idx * 0.1,
            "lon": -112.0 + idx * 0.1,
            "time": "2026-05-17T12:00:00Z",
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _names_in_column(client: TestClient, board_id: str, column_id: str) -> list[str]:
    r = client.get(f"/v1/targets?board_id={board_id}&column_id={column_id}")
    assert r.status_code == 200
    return [t["name"] for t in r.json()]


# Removed test_create_appends_to_bottom — it asserted ["A","B","C"] which
# is also the natural insertion order returned by SQLite even when the
# position column is absent, so it passed against reverted impl. The
# behaviour of "later inserts appear after earlier ones" is already
# proved by test_reorder_to_top (an explicit reorder must rearrange,
# which requires the position-based ORDER BY).


def test_reorder_to_top(client: TestClient) -> None:
    board_id, col_id = _make_board(client)
    a = _make_target(client, board_id, col_id, "A")
    _ = _make_target(client, board_id, col_id, "B")
    c = _make_target(client, board_id, col_id, "C")
    r = client.post(
        f"/v1/targets/{c}/reorder",
        json={"column_id": col_id, "after_id": None},
    )
    assert r.status_code == 200, r.text
    assert _names_in_column(client, board_id, col_id) == ["C", "A", "B"]
    # Idempotent — repeat keeps it on top.
    r = client.post(
        f"/v1/targets/{a}/reorder",
        json={"column_id": col_id, "after_id": None},
    )
    assert r.status_code == 200
    assert _names_in_column(client, board_id, col_id) == ["A", "C", "B"]


def test_reorder_middle(client: TestClient) -> None:
    board_id, col_id = _make_board(client)
    a = _make_target(client, board_id, col_id, "A")
    _ = _make_target(client, board_id, col_id, "B")
    _ = _make_target(client, board_id, col_id, "C")
    _ = _make_target(client, board_id, col_id, "D")
    # Move A to between C and D — after_id=C
    c_id = client.get(f"/v1/targets?board_id={board_id}&column_id={col_id}").json()[2]["id"]
    r = client.post(
        f"/v1/targets/{a}/reorder",
        json={"column_id": col_id, "after_id": c_id},
    )
    assert r.status_code == 200, r.text
    assert _names_in_column(client, board_id, col_id) == ["B", "C", "A", "D"]


def test_reorder_to_bottom(client: TestClient) -> None:
    board_id, col_id = _make_board(client)
    a = _make_target(client, board_id, col_id, "A")
    _ = _make_target(client, board_id, col_id, "B")
    _ = _make_target(client, board_id, col_id, "C")
    # Move A after C (the last).
    c_id = client.get(f"/v1/targets?board_id={board_id}&column_id={col_id}").json()[2]["id"]
    r = client.post(
        f"/v1/targets/{a}/reorder",
        json={"column_id": col_id, "after_id": c_id},
    )
    assert r.status_code == 200
    assert _names_in_column(client, board_id, col_id) == ["B", "C", "A"]


def test_reorder_404_on_missing_anchor(client: TestClient) -> None:
    board_id, col_id = _make_board(client)
    a = _make_target(client, board_id, col_id, "A")
    bogus = "00000000-0000-0000-0000-000000000000"
    r = client.post(
        f"/v1/targets/{a}/reorder",
        json={"column_id": col_id, "after_id": bogus},
    )
    assert r.status_code == 404


def test_reorder_emits_audit_event(client: TestClient) -> None:
    board_id, col_id = _make_board(client)
    a = _make_target(client, board_id, col_id, "A")
    _ = _make_target(client, board_id, col_id, "B")
    b_id = client.get(f"/v1/targets?board_id={board_id}&column_id={col_id}").json()[1]["id"]
    r = client.post(
        f"/v1/targets/{a}/reorder",
        json={"column_id": col_id, "after_id": b_id},
    )
    assert r.status_code == 200
    audit = client.get(f"/v1/audit?target_id={a}").json()
    types = [e["event_type"] for e in audit]
    assert "reordered" in types


def test_viewer_cannot_reorder(client: TestClient) -> None:
    """Reorder is an operator-tier action. A viewer/observer attempting
    to reorder must get 403 — the route is privileged because reorder
    affects shared workspace state (other users see the change in
    realtime), not just a personal preference.

    Backfilled after the mutation audit found that no test exercised
    the role-check on /reorder; removing require_role from the
    endpoint passed every test we had.
    """
    board_id, col_id = _make_board(client)
    a = _make_target(client, board_id, col_id, "A")
    _ = _make_target(client, board_id, col_id, "B")

    # Provision a viewer user and log in as them.
    from datetime import UTC, datetime

    from sqlmodel import Session, select

    from target_workspace.api.auth import hash_password
    from target_workspace.db import get_engine
    from target_workspace.db.tables import UserTable, WorkspaceTable

    with Session(get_engine()) as s:
        s.expire_on_commit = False
        ws = s.exec(select(WorkspaceTable)).first()
        assert ws is not None
        s.add(
            UserTable(
                workspace_id=ws.id,
                email="viewer@example.com",
                display_name="View",
                role="viewer",
                password_hash=hash_password("test-pw"),
                created_at=datetime.now(tz=UTC),
            )
        )
        s.commit()

    client.post("/v1/auth/logout")
    r = client.post(
        "/v1/auth/login",
        json={"email": "viewer@example.com", "password": "test-pw"},
    )
    assert r.status_code == 200

    r = client.post(
        f"/v1/targets/{a}/reorder",
        json={"column_id": col_id, "after_id": None},
    )
    assert r.status_code == 403, f"viewer must not be able to reorder; got {r.status_code} {r.text}"
