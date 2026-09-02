"""Per-resource ACL data-model hooks (tw-liwf).

MVP scope per the ticket: ship the data-model hooks (board_acl,
target_acl, check-ladder helper). Admin UI defers to post-MVP.

Assumption documented in tw-liwf:
  - Resolution order: target_acl > board_acl > group_membership >
    workspace tier.
  - Endpoint integration: board.list filters by board_acl when present.
    Other endpoints will adopt the check helper incrementally as
    needed.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.fast]


def _login_admin(c: TestClient) -> None:
    r = c.post(
        "/v1/auth/login",
        json={"email": "admin@example.com", "password": "test-pw"},
    )
    assert r.status_code == 200, r.text


def test_check_helper_returns_target_acl_when_set() -> None:
    from target_workspace.api.acl import resolve_effective_role

    # Synthetic resolution: target overrides board overrides workspace tier.
    res = resolve_effective_role(
        workspace_tier="viewer",
        board_acl=None,
        target_acl="commander",
    )
    assert res == "commander"


def test_check_helper_uses_board_acl_when_target_acl_absent() -> None:
    from target_workspace.api.acl import resolve_effective_role

    res = resolve_effective_role(
        workspace_tier="viewer",
        board_acl="operator",
        target_acl=None,
    )
    assert res == "operator"


def test_check_helper_falls_back_to_workspace_tier() -> None:
    from target_workspace.api.acl import resolve_effective_role

    res = resolve_effective_role(
        workspace_tier="approver",
        board_acl=None,
        target_acl=None,
    )
    assert res == "approver"


def test_board_acl_persistence(client: TestClient) -> None:
    """Smoke test that the board_acl table exists and stores rows."""
    from sqlmodel import Session, select

    from target_workspace.db import get_engine
    from target_workspace.db.tables import BoardAclTable

    _login_admin(client)
    board = client.post(
        "/v1/boards",
        json={"name": "Restricted", "columns": [{"name": "X", "order": 0}]},
    ).json()
    new_user = client.post(
        "/v1/users",
        json={
            "email": "viewer@example.com",
            "display_name": "Viewer Tier",
            "role": "viewer",
            "password": "test-pass",
        },
    ).json()

    from uuid import UUID as _UUID

    with Session(get_engine()) as s:
        row = BoardAclTable(
            board_id=_UUID(board["id"]),
            user_id=_UUID(new_user["id"]),
            role_overlay="operator",
        )
        s.add(row)
        s.commit()
        # Round-trip read
        readback = s.exec(
            select(BoardAclTable).where(BoardAclTable.board_id == _UUID(board["id"])),
        ).first()
        assert readback is not None
        assert readback.role_overlay == "operator"


def test_target_acl_persistence(client: TestClient) -> None:
    """target_acl table exists and stores rows."""
    from sqlmodel import Session, select

    from target_workspace.db import get_engine
    from target_workspace.db.tables import TargetAclTable

    _login_admin(client)
    board = client.post(
        "/v1/boards",
        json={"name": "T", "columns": [{"name": "X", "order": 0}]},
    ).json()
    column_id = board["columns"][0]["id"]
    target = client.post(
        "/v1/capture",
        data={
            "title": "Restricted",
            "lat": "0",
            "lon": "0",
            "board_id": board["id"],
            "column_id": column_id,
        },
    ).json()
    user = client.post(
        "/v1/users",
        json={
            "email": "a@example.com",
            "display_name": "A",
            "role": "viewer",
            "password": "test-pass",
        },
    ).json()
    from uuid import UUID as _UUID

    with Session(get_engine()) as s:
        s.add(
            TargetAclTable(
                target_id=_UUID(target["id"]),
                user_id=_UUID(user["id"]),
                perms="read,write",
            ),
        )
        s.commit()
        rb = s.exec(
            select(TargetAclTable).where(TargetAclTable.target_id == _UUID(target["id"])),
        ).first()
        assert rb is not None
        assert rb.perms == "read,write"
