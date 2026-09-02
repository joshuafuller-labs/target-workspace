"""RBAC tests — verify role-based 403s.

Asserts that lower-tier users get a clear 403 with role-name in the
detail, and that approval-gated columns gate on `approver+` even for
operators. The seeded bootstrap admin keeps everything green; non-admin
users have to be hand-rolled in the DB for this test because there's no
admin-user-management endpoint yet (tw-?? when we get there).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.fast]


def _login_admin(client: TestClient) -> None:
    r = client.post(
        "/v1/auth/login",
        json={"email": "admin@example.com", "password": "test-pw"},
    )
    assert r.status_code == 200


def _create_user_with_role(role: str) -> dict[str, str]:
    """Provision a user at the given role via direct DB write (no admin
    UI yet). Returns dict with login creds."""
    from sqlmodel import (
        Session,
        select,
    )

    from target_workspace.api.auth import hash_password
    from target_workspace.db import get_engine
    from target_workspace.db.tables import UserTable, WorkspaceTable

    email = f"{role}@example.com"
    password = "test-pw"
    with Session(get_engine()) as session:
        session.expire_on_commit = False
        ws = session.exec(select(WorkspaceTable)).first()
        assert ws is not None, "bootstrap workspace must exist"
        user = UserTable(
            workspace_id=ws.id,
            email=email,
            display_name=role.title(),
            role=role,
            password_hash=hash_password(password),
            created_at=datetime.now(tz=UTC),
        )
        session.add(user)
        session.commit()
    return {"email": email, "password": password}


def _login_as(client: TestClient, role: str) -> None:
    creds = _create_user_with_role(role)
    r = client.post("/v1/auth/login", json=creds)
    assert r.status_code == 200, r.text


def _create_board_as_admin(client: TestClient) -> dict[str, Any]:
    _login_admin(client)
    r = client.post(
        "/v1/boards",
        json={
            "name": "F3EAD",
            "columns": [
                {"name": "FIND", "order": 0},
                {"name": "FIX", "order": 1},
                {"name": "FINISH", "order": 2, "requires_approval": True},
            ],
        },
    )
    assert r.status_code == 201, r.text
    out: dict[str, Any] = r.json()
    return out


def _iso_now() -> str:
    return datetime.now(tz=UTC).isoformat()


def test_viewer_cannot_create_target(client: TestClient) -> None:
    board = _create_board_as_admin(client)
    _login_as(client, "viewer")
    r = client.post(
        "/v1/targets",
        json={
            "board_id": board["id"],
            "column_id": board["columns"][0]["id"],
            "name": "X",
            "lat": 0.0,
            "lon": 0.0,
            "time": _iso_now(),
        },
    )
    assert r.status_code == 403
    assert "observer" in r.json()["detail"]


def test_observer_can_create_but_not_edit_target(client: TestClient) -> None:
    board = _create_board_as_admin(client)
    # Admin creates a target first
    r = client.post(
        "/v1/targets",
        json={
            "board_id": board["id"],
            "column_id": board["columns"][0]["id"],
            "name": "PROBE",
            "lat": 0.0,
            "lon": 0.0,
            "time": _iso_now(),
        },
    )
    target_id = r.json()["id"]

    _login_as(client, "observer")
    # Can create
    r = client.post(
        "/v1/targets",
        json={
            "board_id": board["id"],
            "column_id": board["columns"][0]["id"],
            "name": "OBS-1",
            "lat": 0.0,
            "lon": 0.0,
            "time": _iso_now(),
        },
    )
    assert r.status_code == 201
    # But cannot patch
    r = client.patch(f"/v1/targets/{target_id}", json={"cot_type": "a-h-A"})
    assert r.status_code == 403
    assert "operator" in r.json()["detail"]


def test_operator_can_move_to_non_gated_column_but_not_to_approval_column(
    client: TestClient,
) -> None:
    board = _create_board_as_admin(client)
    find_col, fix_col, finish_col = board["columns"]
    r = client.post(
        "/v1/targets",
        json={
            "board_id": board["id"],
            "column_id": find_col["id"],
            "name": "OP-TEST",
            "lat": 0.0,
            "lon": 0.0,
            "time": _iso_now(),
        },
    )
    target_id = r.json()["id"]

    _login_as(client, "operator")
    # Move FIND → FIX: allowed
    r = client.post(
        f"/v1/targets/{target_id}/move",
        json={"column_id": fix_col["id"]},
    )
    assert r.status_code == 200, r.text
    # Move FIX → FINISH (approval-gated): denied
    r = client.post(
        f"/v1/targets/{target_id}/move",
        json={"column_id": finish_col["id"], "approving_role": "OPS-O"},
    )
    assert r.status_code == 403
    assert "approver" in r.json()["detail"]


def test_approver_can_satisfy_approval_gate_when_operator_cannot(
    client: TestClient,
) -> None:
    """CONTRAST test: same move, two roles, opposite outcomes.

    Previously this was a positive-only assertion (`approver gets 200`),
    which passed even when RBAC was reverted because without role checks
    EVERYONE returns 200 on a move. The TDD-validated form asserts both
    halves so the test only passes when the role check is actually in
    place: operator returns 403 on a gated move, approver with an
    explicit approving_role returns 200.
    """
    board = _create_board_as_admin(client)
    find_col, _fix_col, finish_col = board["columns"]
    # Set up the target as admin so the target exists before role-checks.
    r = client.post(
        "/v1/targets",
        json={
            "board_id": board["id"],
            "column_id": find_col["id"],
            "name": "APP-TEST",
            "lat": 0.0,
            "lon": 0.0,
            "time": _iso_now(),
        },
    )
    target_id = r.json()["id"]

    # Negative half: operator must NOT be able to move into an
    # approval-gated column even with an approving_role string supplied —
    # the gate isn't about the string, it's about the caller's tier.
    _login_as(client, "operator")
    r = client.post(
        f"/v1/targets/{target_id}/move",
        json={"column_id": finish_col["id"], "approving_role": "OPS-O"},
    )
    assert r.status_code == 403, (
        f"operator must be blocked from approval-gated move; got {r.status_code} {r.text}"
    )

    # Positive half: approver+ CAN do the same move with the same
    # approving_role string. The contrast is what proves RBAC is doing
    # its job, not the success.
    _login_as(client, "approver")
    r = client.post(
        f"/v1/targets/{target_id}/move",
        json={"column_id": finish_col["id"], "approving_role": "OPS-O"},
    )
    assert r.status_code == 200, r.text


def test_operator_cannot_create_board(client: TestClient) -> None:
    _login_admin(client)  # bootstrap workspace
    _login_as(client, "operator")
    r = client.post(
        "/v1/boards",
        json={
            "name": "X",
            "columns": [{"name": "A", "order": 0}],
        },
    )
    assert r.status_code == 403
    assert "commander" in r.json()["detail"]


def test_unknown_role_falls_back_to_viewer(client: TestClient) -> None:
    """A user assigned an unrecognised role string MUST be treated as
    viewer (least privilege), not max privilege.

    This test exists because the mutation audit found that flipping
    role_rank's unknown-role fallback from 0 → 99 survived: no other
    test exercised the unknown-role path. A user provisioned with a
    typo or stale role string could otherwise gain admin power.
    """
    board = _create_board_as_admin(client)
    find_col = board["columns"][0]
    _login_as(client, "totally-bogus-role-name")
    r = client.post(
        "/v1/targets",
        json={
            "board_id": board["id"],
            "column_id": find_col["id"],
            "name": "X",
            "lat": 0.0,
            "lon": 0.0,
            "time": _iso_now(),
        },
    )
    assert r.status_code == 403, f"unknown role must fall back to viewer; got {r.status_code}"
