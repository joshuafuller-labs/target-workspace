"""Cross-board target linking — shared-identity + per-board state (tw-v8s).

Per ADR 0017: one canonical target row, plus a target_board_link join
table. A target appears on a board iff a non-tombstoned link exists.
column_id and position are per-board.

MVP scope (sharpened by tw-n0b4 / ADR 0017): schema portion only. The
'Send to board' UX defers to v1.1.

Assumption documented in tw-v8s:
  - target.board_id and target.column_id remain populated and represent
    the canonical/originating board+column ('home'). Additional boards
    show the same target through target_board_link rows.
  - removed_at soft-deletes the link; hard delete is admin-only.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.fast]


def _login_admin(c: TestClient) -> None:
    r = c.post(
        "/v1/auth/login",
        json={"email": "admin@example.com", "password": "test-pw"},
    )
    assert r.status_code == 200, r.text


def _create_target(client: TestClient) -> tuple[UUID, UUID, UUID]:
    _login_admin(client)
    board_response = client.post(
        "/v1/boards",
        json={
            "name": "Linked Board",
            "columns": [
                {"name": "Find", "order": 0},
                {"name": "Fix", "order": 1},
            ],
        },
    )
    assert board_response.status_code == 201, board_response.text
    board = board_response.json()
    column_id = board["columns"][0]["id"]

    target_response = client.post(
        "/v1/targets",
        json={
            "board_id": board["id"],
            "column_id": column_id,
            "name": "Linked target",
            "lat": 0.0,
            "lon": 0.0,
            "time": datetime.now(tz=UTC).isoformat(),
        },
    )
    assert target_response.status_code == 201, target_response.text
    return UUID(target_response.json()["id"]), UUID(board["id"]), UUID(column_id)


def test_target_board_link_table_persists_link(client: TestClient) -> None:
    """The schema slot ships. A target can appear on multiple boards
    via the join table."""
    from sqlmodel import Session, select

    from target_workspace.db import get_engine
    from target_workspace.db.tables import TargetBoardLinkTable

    target_id, board_id, column_id = _create_target(client)

    with Session(get_engine()) as s:
        s.add(
            TargetBoardLinkTable(
                target_id=target_id,
                board_id=board_id,
                column_id=column_id,
                position=0,
                added_at=datetime.now(tz=UTC),
                status="active",
            ),
        )
        s.commit()
        rb = s.exec(
            select(TargetBoardLinkTable).where(
                TargetBoardLinkTable.target_id == target_id,
            ),
        ).first()
        assert rb is not None
        assert rb.column_id == column_id
        assert rb.removed_at is None


def test_soft_delete_marks_link_removed(client: TestClient) -> None:
    from sqlmodel import Session, select

    from target_workspace.db import get_engine
    from target_workspace.db.tables import TargetBoardLinkTable

    target_id, board_id, column_id = _create_target(client)

    with Session(get_engine()) as s:
        row = TargetBoardLinkTable(
            target_id=target_id,
            board_id=board_id,
            column_id=column_id,
            position=0,
            added_at=datetime.now(tz=UTC),
            status="active",
        )
        s.add(row)
        s.commit()

        row.removed_at = datetime.now(tz=UTC)
        row.status = "removed"
        s.add(row)
        s.commit()

        rb = s.exec(
            select(TargetBoardLinkTable).where(
                TargetBoardLinkTable.target_id == target_id,
            ),
        ).first()
        assert rb is not None
        assert rb.removed_at is not None
        assert rb.status == "removed"


def test_workspace_endpoint_unaffected_smoke(client: TestClient) -> None:
    """Sanity: the migration didn't break existing endpoints."""
    _login_admin(client)
    r = client.get("/v1/boards")
    assert r.status_code == 200
