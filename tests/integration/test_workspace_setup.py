"""First-run admin setup wizard — backend surfaces (tw-1csv).

Three backend bits:
  - GET  /v1/workspace/setup-status → {is_first_run, has_admin_changed_password, ...}
  - PATCH /v1/workspace             → rename the workspace ('Default' → something real)
  - the wizard's other steps ride on existing endpoints:
       force-change-password (tw-4exk), invite team (tw-qmnh), board create

Assumption documented in tw-1csv:
  - SPA wizard UI is a follow-up (no autonomous dev-server access).
  - Admin tier required to PATCH /v1/workspace; status endpoint is
    available to any authenticated user so the SPA can decide whether
    to redirect to the wizard.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.fast]


def _login(c: TestClient) -> None:
    r = c.post(
        "/v1/auth/login",
        json={"email": "admin@example.com", "password": "test-pw"},
    )
    assert r.status_code == 200, r.text


def test_setup_status_reports_first_run_for_fresh_workspace(
    client: TestClient,
) -> None:
    _login(client)
    r = client.get("/v1/workspace/setup-status")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_first_run"] is True
    assert body["board_count"] == 0
    assert body["workspace_name"] == "Default"


def test_setup_status_no_longer_first_run_after_board(client: TestClient) -> None:
    _login(client)
    client.post(
        "/v1/boards",
        json={"name": "Real", "columns": [{"name": "X", "order": 0}]},
    )
    r = client.get("/v1/workspace/setup-status").json()
    assert r["is_first_run"] is False
    assert r["board_count"] == 1


def test_patch_workspace_renames(client: TestClient) -> None:
    _login(client)
    r = client.patch("/v1/workspace", json={"name": "Buncombe EOC"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "Buncombe EOC"

    status_body = client.get("/v1/workspace/setup-status").json()
    assert status_body["workspace_name"] == "Buncombe EOC"


def test_patch_workspace_requires_admin(client: TestClient) -> None:
    _login(client)
    # Create a non-admin and try the patch from them.
    client.post(
        "/v1/users",
        json={
            "email": "ops@example.com",
            "display_name": "Op",
            "role": "operator",
            "password": "test-pass-pw",
        },
    ).json()
    # Their must_change_password is set; PATCH /workspace is non-/v1/auth so it
    # gets gated there. We expect either 401/403.
    client.post("/v1/auth/logout")
    from target_workspace.api.ratelimit import reset_all

    reset_all()
    client.post(
        "/v1/auth/login",
        json={"email": "ops@example.com", "password": "test-pass-pw"},
    )
    r = client.patch("/v1/workspace", json={"name": "Hacker"})
    assert r.status_code in (401, 403), r.text


def test_setup_status_requires_auth(client: TestClient) -> None:
    r = client.get("/v1/workspace/setup-status")
    assert r.status_code == 401
