"""Tests for the user-administration API (tw-41on).

Today the bootstrap admin is the only account. To onboard a team
without password-sharing we need:

  POST   /v1/users               commander+ creates a user with role
  GET    /v1/users               list workspace users
  GET    /v1/users/{id}          fetch one
  PATCH  /v1/users/{id}          rename / re-role
  POST   /v1/users/{id}/disable  block login without deleting
  POST   /v1/users/{id}/enable   re-enable
  DELETE /v1/users/{id}          admin-only soft delete

Safety: refuse to delete or disable the last admin (would lock the
workspace out). Disabled / deleted users cannot log in.

TDD-first.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.fast]


@pytest.fixture
def client(authenticated_client: TestClient) -> TestClient:
    return authenticated_client


def _login(client: TestClient, email: str, password: str) -> int:
    r = client.post(
        "/v1/auth/login",
        json={"email": email, "password": password},
    )
    return r.status_code


# ── CREATE ───────────────────────────────────────────────────────────


def test_create_user_requires_commander(client: TestClient) -> None:
    """Make an operator-tier user via direct DB (no admin UI yet),
    log in as them, attempt to create another user → 403."""
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
                email="op@example.com",
                display_name="Op",
                role="operator",
                password_hash=hash_password("pw"),
                created_at=datetime.now(tz=UTC),
            )
        )
        s.commit()

    client.post("/v1/auth/logout")
    client.post("/v1/auth/login", json={"email": "op@example.com", "password": "pw"})
    r = client.post(
        "/v1/users",
        json={"email": "x@example.com", "display_name": "X", "role": "observer", "password": "pw"},
    )
    assert r.status_code == 403


def test_create_user_happy_path(client: TestClient) -> None:
    r = client.post(
        "/v1/users",
        json={
            "email": "new@example.com",
            "display_name": "New User",
            "role": "operator",
            "password": "temp-pw-123",
        },
    )
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["email"] == "new@example.com"
    assert out["display_name"] == "New User"
    assert out["role"] == "operator"
    # Password must NEVER appear in the response.
    assert "password" not in out
    assert "password_hash" not in out
    # New user can log in with the temp password.
    client.post("/v1/auth/logout")
    assert _login(client, "new@example.com", "temp-pw-123") == 200


def test_create_user_duplicate_email_is_409(client: TestClient) -> None:
    client.post(
        "/v1/users",
        json={
            "email": "dup@example.com",
            "display_name": "A",
            "role": "viewer",
            "password": "test-pass",
        },
    )
    r = client.post(
        "/v1/users",
        json={
            "email": "dup@example.com",
            "display_name": "B",
            "role": "viewer",
            "password": "test-pass",
        },
    )
    assert r.status_code == 409


def test_create_user_invalid_role_is_422(client: TestClient) -> None:
    r = client.post(
        "/v1/users",
        json={
            "email": "bad@example.com",
            "display_name": "B",
            "role": "supreme-leader",
            "password": "test-pass",
        },
    )
    assert r.status_code == 422


# ── LIST + GET ───────────────────────────────────────────────────────


def test_list_users_returns_workspace_scoped(client: TestClient) -> None:
    client.post(
        "/v1/users",
        json={
            "email": "u1@example.com",
            "display_name": "U1",
            "role": "viewer",
            "password": "test-pass",
        },
    )
    client.post(
        "/v1/users",
        json={
            "email": "u2@example.com",
            "display_name": "U2",
            "role": "viewer",
            "password": "test-pass",
        },
    )
    r = client.get("/v1/users")
    assert r.status_code == 200
    emails = sorted(u["email"] for u in r.json())
    # Bootstrap admin + 2 created.
    assert "admin@example.com" in emails
    assert "u1@example.com" in emails
    assert "u2@example.com" in emails


def test_get_user_by_id(client: TestClient) -> None:
    created = client.post(
        "/v1/users",
        json={
            "email": "g@example.com",
            "display_name": "G",
            "role": "observer",
            "password": "test-pass",
        },
    ).json()
    r = client.get(f"/v1/users/{created['id']}")
    assert r.status_code == 200
    assert r.json()["email"] == "g@example.com"


def test_get_user_404(client: TestClient) -> None:
    r = client.get("/v1/users/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


# ── PATCH ────────────────────────────────────────────────────────────


def test_patch_user_changes_display_name_and_role(client: TestClient) -> None:
    created = client.post(
        "/v1/users",
        json={
            "email": "p@example.com",
            "display_name": "P",
            "role": "viewer",
            "password": "test-pass",
        },
    ).json()
    r = client.patch(
        f"/v1/users/{created['id']}",
        json={"display_name": "Patched", "role": "operator"},
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["display_name"] == "Patched"
    assert out["role"] == "operator"


def test_patch_empty_body_is_400(client: TestClient) -> None:
    created = client.post(
        "/v1/users",
        json={
            "email": "p2@example.com",
            "display_name": "P",
            "role": "viewer",
            "password": "test-pass",
        },
    ).json()
    r = client.patch(f"/v1/users/{created['id']}", json={})
    assert r.status_code == 400


# ── DISABLE / ENABLE ─────────────────────────────────────────────────


def test_disable_blocks_login(client: TestClient) -> None:
    created = client.post(
        "/v1/users",
        json={
            "email": "d@example.com",
            "display_name": "D",
            "role": "viewer",
            "password": "test-pass",
        },
    ).json()
    r = client.post(f"/v1/users/{created['id']}/disable")
    assert r.status_code == 200
    # Now login as the disabled user → 401 / 403 (we accept either).
    client.post("/v1/auth/logout")
    r = client.post(
        "/v1/auth/login",
        json={"email": "d@example.com", "password": "test-pass"},
    )
    assert r.status_code in {401, 403}, r.text


def test_enable_restores_login(client: TestClient) -> None:
    created = client.post(
        "/v1/users",
        json={
            "email": "e@example.com",
            "display_name": "E",
            "role": "viewer",
            "password": "test-pass",
        },
    ).json()
    client.post(f"/v1/users/{created['id']}/disable")
    r = client.post(f"/v1/users/{created['id']}/enable")
    assert r.status_code == 200
    client.post("/v1/auth/logout")
    assert _login(client, "e@example.com", "test-pass") == 200


# ── DELETE / safety gates ────────────────────────────────────────────


def test_soft_delete_removes_from_list(client: TestClient) -> None:
    created = client.post(
        "/v1/users",
        json={
            "email": "del@example.com",
            "display_name": "D",
            "role": "viewer",
            "password": "test-pass",
        },
    ).json()
    r = client.delete(f"/v1/users/{created['id']}")
    assert r.status_code == 204
    listing = client.get("/v1/users").json()
    assert all(u["email"] != "del@example.com" for u in listing)


def test_delete_last_admin_refused(client: TestClient) -> None:
    """The bootstrap admin is the only admin. DELETE on them must
    return 409 (otherwise the workspace is permanently locked out)."""
    listing = client.get("/v1/users").json()
    bootstrap = next(u for u in listing if u["email"] == "admin@example.com")
    r = client.delete(f"/v1/users/{bootstrap['id']}")
    assert r.status_code == 409
    assert "admin" in r.json().get("detail", "").lower()


def test_disable_last_admin_refused(client: TestClient) -> None:
    """Same safety as delete — disabling the last admin locks out the
    workspace."""
    listing = client.get("/v1/users").json()
    bootstrap = next(u for u in listing if u["email"] == "admin@example.com")
    r = client.post(f"/v1/users/{bootstrap['id']}/disable")
    assert r.status_code == 409


def test_delete_requires_admin_role(client: TestClient) -> None:
    """DELETE is admin-only (one tier above commander). A commander
    can disable a user but not delete them."""
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
                email="cmd@example.com",
                display_name="Cmd",
                role="commander",
                password_hash=hash_password("pw"),
                created_at=datetime.now(tz=UTC),
            )
        )
        s.commit()

    # Create a victim while still admin.
    victim = client.post(
        "/v1/users",
        json={
            "email": "v@example.com",
            "display_name": "V",
            "role": "viewer",
            "password": "test-pass",
        },
    ).json()

    client.post("/v1/auth/logout")
    client.post(
        "/v1/auth/login",
        json={"email": "cmd@example.com", "password": "pw"},
    )
    r = client.delete(f"/v1/users/{victim['id']}")
    assert r.status_code == 403


def test_create_user_with_admin_role_requires_admin(client: TestClient) -> None:
    """Privilege escalation guard: commander can create operator-tier
    users but NOT admin-tier ones (would let them then leverage the
    new admin to delete the bootstrap admin)."""
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
                email="c2@example.com",
                display_name="Cmd",
                role="commander",
                password_hash=hash_password("pw"),
                created_at=datetime.now(tz=UTC),
            )
        )
        s.commit()

    client.post("/v1/auth/logout")
    client.post("/v1/auth/login", json={"email": "c2@example.com", "password": "pw"})
    r = client.post(
        "/v1/users",
        json={
            "email": "new-admin@example.com",
            "display_name": "X",
            "role": "admin",
            "password": "test-pass",
        },
    )
    assert r.status_code == 403
