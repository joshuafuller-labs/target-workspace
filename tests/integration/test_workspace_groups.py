"""Workspace groups — sub-org abstraction (tw-icj8).

Per ADR 0015 the multi-org model is groups-in-workspace (not full
multi-tenancy). Schema slot ships in MVP so post-MVP UX for sub-org
self-service composes cleanly.

Assumption documented in tw-icj8:
  - Group ACL ladder (group_member → board access) integrates with
    tw-liwf hooks when those land. MVP just persists the group +
    membership.
  - Group admin UI is post-MVP.
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


def test_admin_can_create_a_group(client: TestClient) -> None:
    _login_admin(client)
    r = client.post(
        "/v1/groups",
        json={"name": "Cajun Navy", "description": "Volunteer SAR detachment"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "Cajun Navy"


def test_list_groups_returns_created_groups(client: TestClient) -> None:
    _login_admin(client)
    client.post("/v1/groups", json={"name": "A"})
    client.post("/v1/groups", json={"name": "B"})
    r = client.get("/v1/groups")
    assert r.status_code == 200
    names = sorted(g["name"] for g in r.json())
    assert names == ["A", "B"]


def test_admin_can_add_user_to_group(client: TestClient) -> None:
    _login_admin(client)
    group = client.post("/v1/groups", json={"name": "Strike Team"}).json()
    user = client.post(
        "/v1/users",
        json={
            "email": "member@example.com",
            "display_name": "Member",
            "role": "operator",
            "password": "test-pass",
        },
    ).json()
    r = client.post(
        f"/v1/groups/{group['id']}/members",
        json={"user_id": user["id"]},
    )
    assert r.status_code == 201, r.text

    members = client.get(f"/v1/groups/{group['id']}/members").json()
    ids = [m["user_id"] for m in members]
    assert user["id"] in ids


def test_remove_member(client: TestClient) -> None:
    _login_admin(client)
    group = client.post("/v1/groups", json={"name": "X"}).json()
    user = client.post(
        "/v1/users",
        json={
            "email": "rm@example.com",
            "display_name": "Removable",
            "role": "viewer",
            "password": "test-pass",
        },
    ).json()
    client.post(f"/v1/groups/{group['id']}/members", json={"user_id": user["id"]})
    r = client.delete(f"/v1/groups/{group['id']}/members/{user['id']}")
    assert r.status_code == 204
    members = client.get(f"/v1/groups/{group['id']}/members").json()
    assert all(m["user_id"] != user["id"] for m in members)


def test_groups_require_auth(client: TestClient) -> None:
    r = client.get("/v1/groups")
    assert r.status_code == 401
