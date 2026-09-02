"""Tests for board PATCH + DELETE (tw-cbz).

Existing API: POST + GET + GET-by-id only. This adds mutation paths
that the SPA needs for the board-builder UI:

- PATCH /v1/boards/{id}  rename / theme / transitions
- DELETE /v1/boards/{id}  with safety gate (refuse if non-empty)

Column add/edit/delete on a live board is intentionally out of scope
here — that's tw-itn. Keeps each bd focused.

TDD-first: every test was written before the impl. Mutation audit
extension to api/routers/boards.py + db/repositories.py covers the
behavioural gates downstream.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.fast]


@pytest.fixture
def client(authenticated_client: TestClient) -> TestClient:
    return authenticated_client


def _new_board(client: TestClient, name: str = "X") -> dict[str, Any]:
    r = client.post(
        "/v1/boards",
        json={
            "name": name,
            "columns": [
                {"name": "Find", "order": 0},
                {"name": "Fix", "order": 1, "requires_approval": True},
                {"name": "Finish", "order": 2},
            ],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


# ── PATCH /v1/boards/{id} ────────────────────────────────────────────


def test_patch_renames_board(client: TestClient) -> None:
    board = _new_board(client, "Original Name")
    r = client.patch(f"/v1/boards/{board['id']}", json={"name": "Renamed"})
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Renamed"
    # Confirms via fresh read — not just the response object.
    r2 = client.get(f"/v1/boards/{board['id']}")
    assert r2.json()["name"] == "Renamed"


def test_patch_changes_theme(client: TestClient) -> None:
    board = _new_board(client)
    r = client.patch(f"/v1/boards/{board['id']}", json={"theme": "ics"})
    assert r.status_code == 200
    assert r.json()["theme"] == "ics"


def test_patch_changes_transition_policy(client: TestClient) -> None:
    board = _new_board(client)
    r = client.patch(
        f"/v1/boards/{board['id']}",
        json={"transitions": "sequential"},
    )
    assert r.status_code == 200
    assert r.json()["transitions"] == "sequential"


def test_patch_empty_body_is_400(client: TestClient) -> None:
    board = _new_board(client)
    r = client.patch(f"/v1/boards/{board['id']}", json={})
    assert r.status_code == 400


def test_patch_missing_board_is_404(client: TestClient) -> None:
    r = client.patch(
        "/v1/boards/00000000-0000-0000-0000-000000000000",
        json={"name": "X"},
    )
    assert r.status_code == 404


def test_patch_does_not_modify_columns(client: TestClient) -> None:
    """Column mutation is a separate bd (tw-itn) — extra/changed
    columns in a PATCH body must be a no-op (or rejected). Keeps
    blast radius small while tw-itn lands."""
    board = _new_board(client)
    orig_columns = board["columns"]
    r = client.patch(
        f"/v1/boards/{board['id']}",
        json={"name": "X", "columns": [{"name": "Surprise", "order": 0}]},
    )
    # Either 400 (rejected) or 200 with original columns preserved.
    assert r.status_code in {200, 400, 422}
    if r.status_code == 200:
        assert r.json()["columns"] == orig_columns


# ── DELETE /v1/boards/{id} ───────────────────────────────────────────


def test_delete_empty_board_succeeds(client: TestClient) -> None:
    board = _new_board(client)
    r = client.delete(f"/v1/boards/{board['id']}")
    assert r.status_code == 204
    # And the board is gone.
    r2 = client.get(f"/v1/boards/{board['id']}")
    assert r2.status_code == 404


def test_delete_missing_board_is_404(client: TestClient) -> None:
    r = client.delete("/v1/boards/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


def test_delete_board_with_targets_is_409(client: TestClient) -> None:
    """Safety gate: don't cascade-delete operational data. Operator
    must move/delete targets first. Returns 409 Conflict with a hint
    in the detail."""
    board = _new_board(client)
    find_col_id = board["columns"][0]["id"]
    # Drop a single target in.
    r = client.post(
        "/v1/targets",
        json={
            "board_id": board["id"],
            "column_id": find_col_id,
            "name": "X",
            "lat": 0.0,
            "lon": 0.0,
            "time": datetime.now(tz=UTC).isoformat(),
        },
    )
    assert r.status_code == 201

    r = client.delete(f"/v1/boards/{board['id']}")
    assert r.status_code == 409, r.text
    # The detail should mention why so the UI can show it.
    detail = r.json().get("detail", "").lower()
    assert "target" in detail or "non-empty" in detail or "not empty" in detail


def test_delete_requires_commander_role(client: TestClient) -> None:
    """Board delete is permanent destructive — gate at commander+.

    Provision an operator (one tier below) and verify they get 403.
    """
    from sqlmodel import Session, select

    from target_workspace.api.auth import hash_password
    from target_workspace.db import get_engine
    from target_workspace.db.tables import UserTable, WorkspaceTable

    board = _new_board(client)

    with Session(get_engine()) as s:
        s.expire_on_commit = False
        ws = s.exec(select(WorkspaceTable)).first()
        assert ws is not None
        s.add(
            UserTable(
                workspace_id=ws.id,
                email="operator@example.com",
                display_name="Op",
                role="operator",
                password_hash=hash_password("pw"),
                created_at=datetime.now(tz=UTC),
            )
        )
        s.commit()

    client.post("/v1/auth/logout")
    client.post(
        "/v1/auth/login",
        json={"email": "operator@example.com", "password": "pw"},
    )
    r = client.delete(f"/v1/boards/{board['id']}")
    assert r.status_code == 403


def test_patch_requires_commander_role(client: TestClient) -> None:
    """Same authorization as DELETE — board configuration is workspace-
    level state that affects every user. operator can't rename."""
    from sqlmodel import Session, select

    from target_workspace.api.auth import hash_password
    from target_workspace.db import get_engine
    from target_workspace.db.tables import UserTable, WorkspaceTable

    board = _new_board(client)

    with Session(get_engine()) as s:
        s.expire_on_commit = False
        ws = s.exec(select(WorkspaceTable)).first()
        assert ws is not None
        s.add(
            UserTable(
                workspace_id=ws.id,
                email="operator2@example.com",
                display_name="Op",
                role="operator",
                password_hash=hash_password("pw"),
                created_at=datetime.now(tz=UTC),
            )
        )
        s.commit()

    client.post("/v1/auth/logout")
    client.post(
        "/v1/auth/login",
        json={"email": "operator2@example.com", "password": "pw"},
    )
    r = client.patch(f"/v1/boards/{board['id']}", json={"name": "X"})
    assert r.status_code == 403
