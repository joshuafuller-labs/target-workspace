"""Map tile URL override (tw-45s).

Backend exposes a settings field + GET /v1/workspace/map-config so the
frontend reads the tile source from the API instead of hard-coding.

Default: empty (frontend falls back to its bundled Natural Earth
tiles when no override is configured).

Assumption documented in tw-45s:
  - Actual Natural Earth tile bundling is a deployment / build step
    (the tile pyramid is 50-200 MB and lives in the container layer,
    not in the API repo). This ticket ships the override mechanism;
    bundling happens in the docker build.
  - Future: per-board tile override + per-user tile override (v1.x).
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.fast]


def _login(c: TestClient) -> None:
    r = c.post(
        "/v1/auth/login",
        json={"email": "admin@example.com", "password": "test-pw"},
    )
    assert r.status_code == 200, r.text


def test_map_config_default_returns_empty_override(client: TestClient) -> None:
    _login(client)
    r = client.get("/v1/workspace/map-config")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "tile_url" in body
    assert body["tile_url"] == ""
    assert body["provider"] == "bundled-natural-earth"


def test_map_config_returns_override_when_env_set(client: TestClient) -> None:
    """TW_MAP_TILE_URL env override is reflected in the response."""
    os.environ["TW_MAP_TILE_URL"] = "https://tiles.example.com/{z}/{x}/{y}.png"
    from target_workspace.api import config as config_module

    config_module.reset_settings_cache()
    try:
        _login(client)
        r = client.get("/v1/workspace/map-config")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["tile_url"] == "https://tiles.example.com/{z}/{x}/{y}.png"
        assert body["provider"] == "override"
    finally:
        os.environ.pop("TW_MAP_TILE_URL", None)
        config_module.reset_settings_cache()
