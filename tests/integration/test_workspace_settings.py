"""Workspace settings mutation API (tw-smc).

GET  /v1/workspaces/me        → current workspace settings
PATCH /v1/workspaces/me       → mutate brand_name / default_theme /
                                freshness window / correlation tolerance

Admin-only on PATCH. GET is any authenticated user.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.fast]


def _login(c: TestClient) -> None:
    r = c.post("/v1/auth/login", json={"email": "admin@example.com", "password": "test-pw"})
    assert r.status_code == 200, r.text


def test_get_workspace_returns_settings(client: TestClient) -> None:
    _login(client)
    r = client.get("/v1/workspaces/me")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "id" in body
    assert "name" in body
    # Default settings shape — all knobs surface with sensible defaults.
    assert "brand_name" in body
    assert "default_theme" in body
    assert "freshness_active_seconds" in body
    assert "freshness_coasting_seconds" in body
    assert "freshness_stale_seconds" in body
    assert "correlation_radius_m" in body


def test_patch_updates_brand_name(client: TestClient) -> None:
    _login(client)
    r = client.patch("/v1/workspaces/me", json={"brand_name": "EOC Watch"})
    assert r.status_code == 200, r.text
    assert r.json()["brand_name"] == "EOC Watch"
    # Persisted across requests
    r2 = client.get("/v1/workspaces/me")
    assert r2.json()["brand_name"] == "EOC Watch"


def test_patch_updates_default_theme(client: TestClient) -> None:
    _login(client)
    r = client.patch("/v1/workspaces/me", json={"default_theme": "ics"})
    assert r.status_code == 200, r.text
    assert r.json()["default_theme"] == "ics"


def test_patch_rejects_bad_theme(client: TestClient) -> None:
    _login(client)
    r = client.patch("/v1/workspaces/me", json={"default_theme": "bogus"})
    assert r.status_code == 422


def test_patch_updates_freshness(client: TestClient) -> None:
    _login(client)
    r = client.patch(
        "/v1/workspaces/me",
        json={
            "freshness_active_seconds": 30,
            "freshness_coasting_seconds": 90,
            "freshness_stale_seconds": 300,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["freshness_active_seconds"] == 30
    assert body["freshness_coasting_seconds"] == 90
    assert body["freshness_stale_seconds"] == 300


def test_patch_updates_correlation_radius(client: TestClient) -> None:
    _login(client)
    r = client.patch("/v1/workspaces/me", json={"correlation_radius_m": 250.0})
    assert r.status_code == 200, r.text
    assert r.json()["correlation_radius_m"] == 250.0


def test_patch_requires_admin(client: TestClient) -> None:
    """A non-admin can GET but not PATCH."""
    _login(client)
    # Create a viewer.
    client.post(
        "/v1/users",
        json={
            "email": "v@example.com",
            "display_name": "V",
            "role": "viewer",
            "password": "tmp-pass-123",
        },
    )
    client.post("/v1/auth/logout")
    client.post(
        "/v1/auth/login",
        json={"email": "v@example.com", "password": "tmp-pass-123"},
    )
    # New users have must_change_password=True; clear it so we can hit
    # the workspace endpoint.
    client.post(
        "/v1/auth/change-password",
        json={"current_password": "tmp-pass-123", "new_password": "another-pass"},
    )
    r_get = client.get("/v1/workspaces/me")
    assert r_get.status_code == 200
    r_patch = client.patch("/v1/workspaces/me", json={"brand_name": "X"})
    assert r_patch.status_code in (401, 403)
