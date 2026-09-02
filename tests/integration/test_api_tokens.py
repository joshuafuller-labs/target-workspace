"""API tokens for service accounts (tw-sodu).

Long-lived bearer tokens for integrations (CI scripts, ATAK plugin,
third-party sensors). Issuance returns the plaintext ONCE; we store
sha256 hash. Authentication via Authorization: Bearer <token>.

Assumption documented in tw-sodu:
  - Tokens are workspace-scoped + bound to a creator. They inherit the
    creator's role at issue time. New tokens carry explicit scopes;
    legacy rows with no scopes are treated as '*' for compatibility.
  - Token expiry is optional. No-expiry tokens are valid until revoked.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
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


def _insert_pending_nomination(
    *,
    target_id: str,
    from_column_id: str,
    to_column_id: str,
) -> str:
    from sqlmodel import select

    from target_workspace.db import get_engine, get_session
    from target_workspace.db.tables import UserTable, WorkflowNominationTable

    with get_session(get_engine()) as session:
        user = session.exec(select(UserTable).where(UserTable.email == "admin@example.com")).one()
        nomination = WorkflowNominationTable(
            workspace_id=user.workspace_id,
            target_id=UUID(target_id),
            from_column_id=UUID(from_column_id),
            to_column_id=UUID(to_column_id),
            proposed_by="policy:presence",
            actor_id=user.id,
            approver_role="supervisor",
            reason="presence arrived",
            evidence_json={"callsign": "BISON-01"},
            created_at=datetime.now(tz=UTC),
        )
        session.add(nomination)
        session.flush()
        return str(nomination.id)


def test_create_token_returns_plaintext_once(client: TestClient) -> None:
    _login_admin(client)
    r = client.post("/v1/auth/tokens", json={"name": "ci-bot"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert "token" in body
    assert len(body["token"]) >= 32
    assert body["name"] == "ci-bot"

    # Listing must NOT show the plaintext anymore.
    r = client.get("/v1/auth/tokens")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) >= 1
    assert "token" not in rows[0]
    # Mask: first 8 chars only
    assert "preview" in rows[0]


def test_bearer_token_authenticates_request(client: TestClient) -> None:
    _login_admin(client)
    token = client.post("/v1/auth/tokens", json={"name": "ci"}).json()["token"]
    client.post("/v1/auth/logout")

    # Cookie cleared — use bearer instead
    r = client.get("/v1/boards", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text


def test_token_scopes_are_created_and_listed(client: TestClient) -> None:
    _login_admin(client)
    r = client.post(
        "/v1/auth/tokens",
        json={"name": "readonly", "scopes": ["boards:read"]},
    )
    assert r.status_code == 201, r.text
    assert r.json()["scopes"] == ["boards:read"]

    r = client.get("/v1/auth/tokens")
    assert r.status_code == 200
    assert r.json()[0]["scopes"] == ["boards:read"]


def test_scoped_token_allows_matching_read_scope(client: TestClient) -> None:
    _login_admin(client)
    token = client.post(
        "/v1/auth/tokens",
        json={"name": "readonly", "scopes": ["boards:read"]},
    ).json()["token"]
    client.post("/v1/auth/logout")

    r = client.get("/v1/boards", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text


def test_board_mutations_require_board_write_scope(client: TestClient) -> None:
    _login_admin(client)
    r = client.post(
        "/v1/boards",
        json={
            "name": "Scoped Board",
            "columns": [
                {"name": "Intake", "order": 0},
                {"name": "Active", "order": 1},
            ],
        },
    )
    assert r.status_code == 201, r.text
    board = r.json()
    board_id = board["id"]
    token = client.post(
        "/v1/auth/tokens",
        json={"name": "board-reader", "scopes": ["boards:read"]},
    ).json()["token"]
    client.post("/v1/auth/logout")
    headers = {"Authorization": f"Bearer {token}"}

    denied_requests = [
        ("patch", f"/v1/boards/{board_id}", {"name": "Denied"}),
        ("post", f"/v1/boards/{board_id}/columns", {"name": "Denied", "order": 2}),
        (
            "patch",
            f"/v1/boards/{board_id}/columns/{board['columns'][0]['id']}",
            {"name": "Denied"},
        ),
        (
            "post",
            f"/v1/boards/{board_id}/columns/reorder",
            {
                "columns": [
                    {"id": board["columns"][0]["id"], "order": 1},
                    {"id": board["columns"][1]["id"], "order": 0},
                ],
            },
        ),
        ("delete", f"/v1/boards/{board_id}/columns/{board['columns'][1]['id']}", None),
        ("delete", f"/v1/boards/{board_id}", None),
    ]
    for method, path, json_body in denied_requests:
        request = getattr(client, method)
        kwargs: dict[str, object] = {"headers": headers}
        if json_body is not None:
            kwargs["json"] = json_body
        r = request(path, **kwargs)
        assert r.status_code == 403, r.text
        assert r.json()["detail"] == "missing required token scope: boards:write"


def test_workspace_settings_and_policy_require_workspace_scopes(client: TestClient) -> None:
    _login_admin(client)
    reader = client.post(
        "/v1/auth/tokens",
        json={"name": "workspace-reader", "scopes": ["workspace:read"]},
    ).json()["token"]
    writer = client.post(
        "/v1/auth/tokens",
        json={"name": "workspace-writer", "scopes": ["workspace:write"]},
    ).json()["token"]
    client.post("/v1/auth/logout")

    read_headers = {"Authorization": f"Bearer {reader}"}
    write_headers = {"Authorization": f"Bearer {writer}"}

    r = client.get("/v1/workspaces/me", headers=read_headers)
    assert r.status_code == 200, r.text
    r = client.get("/v1/workspace/mfa-policy", headers=read_headers)
    assert r.status_code == 200, r.text

    r = client.patch(
        "/v1/workspaces/me",
        headers=read_headers,
        json={"brand_name": "Denied Workspace"},
    )
    assert r.status_code == 403, r.text
    assert r.json()["detail"] == "missing required token scope: workspace:write"

    r = client.put(
        "/v1/workspace/mfa-policy",
        headers=read_headers,
        json={"required_for_roles": ["admin"]},
    )
    assert r.status_code == 403, r.text
    assert r.json()["detail"] == "missing required token scope: workspace:write"

    r = client.patch(
        "/v1/workspaces/me",
        headers=write_headers,
        json={"brand_name": "Allowed Workspace"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["brand_name"] == "Allowed Workspace"

    r = client.put(
        "/v1/workspace/mfa-policy",
        headers=write_headers,
        json={"required_for_roles": ["admin"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["required_for_roles"] == ["admin"]


def test_workspace_utility_and_export_routes_require_workspace_scopes(
    client: TestClient,
) -> None:
    _login_admin(client)
    reader = client.post(
        "/v1/auth/tokens",
        json={"name": "workspace-reader", "scopes": ["workspace:read"]},
    ).json()["token"]
    writer = client.post(
        "/v1/auth/tokens",
        json={"name": "workspace-writer", "scopes": ["workspace:write"]},
    ).json()["token"]
    exporter = client.post(
        "/v1/auth/tokens",
        json={"name": "workspace-exporter", "scopes": ["workspace:export"]},
    ).json()["token"]
    client.post("/v1/auth/logout")

    read_headers = {"Authorization": f"Bearer {reader}"}
    write_headers = {"Authorization": f"Bearer {writer}"}
    export_headers = {"Authorization": f"Bearer {exporter}"}

    for path in (
        "/v1/workspace/setup-status",
        "/v1/workspace/demo-scenarios",
        "/v1/workspace/map-config",
    ):
        r = client.get(path, headers=read_headers)
        assert r.status_code == 200, r.text

    r = client.patch("/v1/workspace", headers=read_headers, json={"name": "Denied"})
    assert r.status_code == 403, r.text
    assert r.json()["detail"] == "missing required token scope: workspace:write"

    r = client.post("/v1/workspace/export", headers=read_headers)
    assert r.status_code == 403, r.text
    assert r.json()["detail"] == "missing required token scope: workspace:export"

    r = client.patch("/v1/workspace", headers=write_headers, json={"name": "Allowed"})
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Allowed"

    r = client.post("/v1/workspace/export", headers=export_headers)
    assert r.status_code == 200, r.text
    assert "application/gzip" in r.headers.get("content-type", "")
    assert r.content


def test_workflow_trigger_routes_require_workflow_scopes(client: TestClient) -> None:
    _login_admin(client)
    r = client.post(
        "/v1/boards",
        json={
            "name": "Workflow Scope Board",
            "columns": [
                {"name": "Assigned", "order": 0},
                {"name": "On-scene", "order": 1},
            ],
        },
    )
    assert r.status_code == 201, r.text
    board = r.json()
    trigger_body = {
        "trigger": "presence.arrived",
        "condition": "min_assignees:1",
        "action_move_to_column_id": board["columns"][1]["id"],
        "justification_template": "{callsign} arrived",
    }
    rule = client.post(
        f"/v1/boards/{board['id']}/workflow-triggers",
        json=trigger_body,
    ).json()
    reader = client.post(
        "/v1/auth/tokens",
        json={"name": "workflow-reader", "scopes": ["workflow:read"]},
    ).json()["token"]
    writer = client.post(
        "/v1/auth/tokens",
        json={"name": "workflow-writer", "scopes": ["workflow:write"]},
    ).json()["token"]
    client.post("/v1/auth/logout")

    read_headers = {"Authorization": f"Bearer {reader}"}
    write_headers = {"Authorization": f"Bearer {writer}"}

    r = client.get(f"/v1/boards/{board['id']}/workflow-triggers", headers=read_headers)
    assert r.status_code == 200, r.text
    assert [row["id"] for row in r.json()] == [rule["id"]]

    r = client.post(
        f"/v1/boards/{board['id']}/workflow-triggers",
        headers=read_headers,
        json=trigger_body,
    )
    assert r.status_code == 403, r.text
    assert r.json()["detail"] == "missing required token scope: workflow:write"

    r = client.patch(
        f"/v1/workflow-triggers/{rule['id']}",
        headers=read_headers,
        json={"condition": "all_assigned"},
    )
    assert r.status_code == 403, r.text
    assert r.json()["detail"] == "missing required token scope: workflow:write"

    r = client.delete(f"/v1/workflow-triggers/{rule['id']}", headers=read_headers)
    assert r.status_code == 403, r.text
    assert r.json()["detail"] == "missing required token scope: workflow:write"

    r = client.post(
        f"/v1/boards/{board['id']}/workflow-triggers",
        headers=write_headers,
        json={**trigger_body, "condition": "all_assigned"},
    )
    assert r.status_code == 200, r.text
    write_rule = r.json()
    assert write_rule["condition"] == "all_assigned"

    r = client.patch(
        f"/v1/workflow-triggers/{write_rule['id']}",
        headers=write_headers,
        json={"condition": "min_assignees:1"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["condition"] == "min_assignees:1"

    r = client.delete(f"/v1/workflow-triggers/{write_rule['id']}", headers=write_headers)
    assert r.status_code == 204, r.text


def test_group_routes_require_group_scopes(client: TestClient) -> None:
    _login_admin(client)
    group = client.post("/v1/groups", json={"name": "Scoped Group"}).json()
    user = client.post(
        "/v1/users",
        json={
            "email": "group-member@example.com",
            "display_name": "Group Member",
            "role": "operator",
            "password": "test-pass",  # pragma: allowlist secret
        },
    ).json()
    reader = client.post(
        "/v1/auth/tokens",
        json={"name": "group-reader", "scopes": ["groups:read"]},
    ).json()["token"]
    writer = client.post(
        "/v1/auth/tokens",
        json={"name": "group-writer", "scopes": ["groups:write"]},
    ).json()["token"]
    client.post("/v1/auth/logout")

    read_headers = {"Authorization": f"Bearer {reader}"}
    write_headers = {"Authorization": f"Bearer {writer}"}

    r = client.get("/v1/groups", headers=read_headers)
    assert r.status_code == 200, r.text
    assert [row["id"] for row in r.json()] == [group["id"]]

    r = client.get(f"/v1/groups/{group['id']}/members", headers=read_headers)
    assert r.status_code == 200, r.text
    assert r.json() == []

    r = client.post("/v1/groups", headers=read_headers, json={"name": "Denied"})
    assert r.status_code == 403, r.text
    assert r.json()["detail"] == "missing required token scope: groups:write"

    r = client.post(
        f"/v1/groups/{group['id']}/members",
        headers=read_headers,
        json={"user_id": user["id"]},
    )
    assert r.status_code == 403, r.text
    assert r.json()["detail"] == "missing required token scope: groups:write"

    r = client.post("/v1/groups", headers=write_headers, json={"name": "Allowed"})
    assert r.status_code == 201, r.text
    assert r.json()["name"] == "Allowed"

    r = client.post(
        f"/v1/groups/{group['id']}/members",
        headers=write_headers,
        json={"user_id": user["id"]},
    )
    assert r.status_code == 201, r.text

    r = client.delete(
        f"/v1/groups/{group['id']}/members/{user['id']}",
        headers=read_headers,
    )
    assert r.status_code == 403, r.text
    assert r.json()["detail"] == "missing required token scope: groups:write"

    r = client.delete(
        f"/v1/groups/{group['id']}/members/{user['id']}",
        headers=write_headers,
    )
    assert r.status_code == 204, r.text


def test_op_period_routes_require_op_period_scopes(client: TestClient) -> None:
    _login_admin(client)
    r = client.post(
        "/v1/boards",
        json={"name": "Op Scope Board", "columns": [{"name": "Active", "order": 0}]},
    )
    assert r.status_code == 201, r.text
    board = r.json()
    opened = client.post(f"/v1/boards/{board['id']}/op-periods", json={}).json()
    reader = client.post(
        "/v1/auth/tokens",
        json={"name": "op-reader", "scopes": ["op_periods:read"]},
    ).json()["token"]
    writer = client.post(
        "/v1/auth/tokens",
        json={"name": "op-writer", "scopes": ["op_periods:write"]},
    ).json()["token"]
    client.post("/v1/auth/logout")

    read_headers = {"Authorization": f"Bearer {reader}"}
    write_headers = {"Authorization": f"Bearer {writer}"}

    r = client.get(f"/v1/boards/{board['id']}/op-periods", headers=read_headers)
    assert r.status_code == 200, r.text
    assert [row["id"] for row in r.json()] == [opened["id"]]

    r = client.post(f"/v1/boards/{board['id']}/op-periods", headers=read_headers, json={})
    assert r.status_code == 403, r.text
    assert r.json()["detail"] == "missing required token scope: op_periods:write"

    r = client.post(f"/v1/boards/{board['id']}/op-periods", headers=write_headers, json={})
    assert r.status_code == 201, r.text
    assert r.json()["number"] == 2


def test_bearer_tokens_cannot_manage_interactive_credentials(client: TestClient) -> None:
    _login_admin(client)
    token = client.post(
        "/v1/auth/tokens",
        json={"name": "full-service-token", "scopes": ["*"]},
    ).json()["token"]
    client.post("/v1/auth/logout")
    headers = {"Authorization": f"Bearer {token}"}

    denied_requests = [
        ("post", "/v1/auth/sessions/revoke-all", None),
        ("post", "/v1/auth/mfa/totp/enroll", None),
        ("post", "/v1/auth/mfa/totp/verify-enroll", {"code": "123456"}),
        (
            "post",
            "/v1/auth/mfa/totp/disable",
            {"password": "test-pw", "code": "123456"},  # pragma: allowlist secret
        ),
        ("get", "/v1/auth/passkeys", None),
        ("post", "/v1/auth/passkeys/register/options", {"name": "Token Key"}),
        ("delete", "/v1/auth/passkeys/00000000-0000-0000-0000-000000000000", None),
    ]
    for method, path, json_body in denied_requests:
        request = getattr(client, method)
        kwargs: dict[str, object] = {"headers": headers}
        if json_body is not None:
            kwargs["json"] = json_body
        r = request(path, **kwargs)
        assert r.status_code == 403, r.text
        assert r.json()["detail"] == "interactive session required"


def test_position_routes_require_position_scopes(client: TestClient) -> None:
    _login_admin(client)
    me = client.get("/v1/auth/me").json()
    positions = client.get("/v1/positions").json()
    incident_commander = next(row for row in positions if row["ics_code"] == "IC")
    reader = client.post(
        "/v1/auth/tokens",
        json={"name": "position-reader", "scopes": ["positions:read"]},
    ).json()["token"]
    writer = client.post(
        "/v1/auth/tokens",
        json={"name": "position-writer", "scopes": ["positions:write"]},
    ).json()["token"]
    client.post("/v1/auth/logout")

    read_headers = {"Authorization": f"Bearer {reader}"}
    write_headers = {"Authorization": f"Bearer {writer}"}

    r = client.get("/v1/positions", headers=read_headers)
    assert r.status_code == 200, r.text
    assert {row["ics_code"] for row in r.json()}

    r = client.get("/v1/positions/current", headers=read_headers)
    assert r.status_code == 200, r.text

    r = client.get(f"/v1/positions/{incident_commander['id']}/history", headers=read_headers)
    assert r.status_code == 200, r.text
    assert r.json() == []

    r = client.post(
        f"/v1/positions/{incident_commander['id']}/assignments",
        headers=read_headers,
        json={"user_id": me["id"]},
    )
    assert r.status_code == 403, r.text
    assert r.json()["detail"] == "missing required token scope: positions:write"

    r = client.post(
        f"/v1/positions/{incident_commander['id']}/assignments",
        headers=write_headers,
        json={"user_id": me["id"]},
    )
    assert r.status_code == 201, r.text
    assert r.json()["user_id"] == me["id"]


def test_operational_telemetry_routes_require_read_scopes(client: TestClient) -> None:
    _login_admin(client)
    board = client.post(
        "/v1/boards",
        json={"name": "Telemetry Board", "columns": [{"name": "Active", "order": 0}]},
    ).json()
    denied = client.post(
        "/v1/auth/tokens",
        json={"name": "boards-only", "scopes": ["boards:read"]},
    ).json()["token"]
    presence_reader = client.post(
        "/v1/auth/tokens",
        json={"name": "presence-reader", "scopes": ["presence:read"]},
    ).json()["token"]
    publisher_reader = client.post(
        "/v1/auth/tokens",
        json={"name": "publisher-reader", "scopes": ["publishers:read"]},
    ).json()["token"]
    metrics_reader = client.post(
        "/v1/auth/tokens",
        json={"name": "metrics-reader", "scopes": ["metrics:read"]},
    ).json()["token"]
    client.post("/v1/auth/logout")

    denied_headers = {"Authorization": f"Bearer {denied}"}
    denied_requests = [
        ("get", "/v1/presence", "presence:read"),
        ("get", "/v1/presence/UNKNOWN", "presence:read"),
        ("get", "/v1/publishers/health", "publishers:read"),
        ("get", f"/v1/metrics/dwell?board_id={board['id']}", "metrics:read"),
    ]
    for method, path, scope in denied_requests:
        r = getattr(client, method)(path, headers=denied_headers)
        assert r.status_code == 403, r.text
        assert r.json()["detail"] == f"missing required token scope: {scope}"

    r = client.get("/v1/presence", headers={"Authorization": f"Bearer {presence_reader}"})
    assert r.status_code == 200, r.text
    assert r.json() == []

    r = client.get(
        "/v1/publishers/health",
        headers={"Authorization": f"Bearer {publisher_reader}"},
    )
    assert r.status_code == 200, r.text
    assert r.json() == []

    r = client.get(
        f"/v1/metrics/dwell?board_id={board['id']}",
        headers={"Authorization": f"Bearer {metrics_reader}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["total_targets"] == 0


def test_templates_forms_invitations_and_safety_require_specific_scopes(
    client: TestClient,
) -> None:
    _login_admin(client)
    board = client.post(
        "/v1/boards",
        json={"name": "Forms Board", "columns": [{"name": "Active", "order": 0}]},
    ).json()
    denied = client.post(
        "/v1/auth/tokens",
        json={"name": "boards-only", "scopes": ["boards:read"]},
    ).json()["token"]
    template_reader = client.post(
        "/v1/auth/tokens",
        json={"name": "template-reader", "scopes": ["templates:read"]},
    ).json()["token"]
    template_writer = client.post(
        "/v1/auth/tokens",
        json={"name": "template-writer", "scopes": ["templates:write"]},
    ).json()["token"]
    forms_reader = client.post(
        "/v1/auth/tokens",
        json={"name": "forms-reader", "scopes": ["forms:read"]},
    ).json()["token"]
    invitation_writer = client.post(
        "/v1/auth/tokens",
        json={"name": "invitation-writer", "scopes": ["invitations:write"]},
    ).json()["token"]
    safety_reader = client.post(
        "/v1/auth/tokens",
        json={"name": "safety-reader", "scopes": ["safety:read"]},
    ).json()["token"]
    client.post("/v1/auth/logout")

    denied_headers = {"Authorization": f"Bearer {denied}"}
    denied_requests = [
        ("get", "/v1/board-templates", None, "templates:read"),
        (
            "post",
            "/v1/board-templates/ics/instantiate",
            {"name": "Denied Template"},
            "templates:write",
        ),
        (
            "post",
            f"/v1/boards/{board['id']}/clone",
            {"name": "Denied Clone"},
            "templates:write",
        ),
        ("get", f"/v1/boards/{board['id']}/forms/ics-214", None, "forms:read"),
        ("get", f"/v1/boards/{board['id']}/forms/ics-209", None, "forms:read"),
        (
            "post",
            "/v1/invitations",
            {"role": "viewer"},
            "invitations:write",
        ),
        ("get", "/v1/safety/stationary", None, "safety:read"),
    ]
    for method, path, json_body, scope in denied_requests:
        request = getattr(client, method)
        kwargs: dict[str, object] = {"headers": denied_headers}
        if json_body is not None:
            kwargs["json"] = json_body
        r = request(path, **kwargs)
        assert r.status_code == 403, r.text
        assert r.json()["detail"] == f"missing required token scope: {scope}"

    r = client.get(
        "/v1/board-templates",
        headers={"Authorization": f"Bearer {template_reader}"},
    )
    assert r.status_code == 200, r.text
    assert {row["id"] for row in r.json()} >= {"ics", "sar"}

    r = client.post(
        "/v1/board-templates/ics/instantiate",
        headers={"Authorization": f"Bearer {template_writer}"},
        json={"name": "Allowed Template"},
    )
    assert r.status_code == 201, r.text

    r = client.get(
        f"/v1/boards/{board['id']}/forms/ics-214",
        headers={"Authorization": f"Bearer {forms_reader}"},
    )
    assert r.status_code == 200, r.text
    assert "ICS-214" in r.text

    r = client.post(
        "/v1/invitations",
        headers={"Authorization": f"Bearer {invitation_writer}"},
        json={"role": "viewer"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["role"] == "viewer"

    r = client.get(
        "/v1/safety/stationary",
        headers={"Authorization": f"Bearer {safety_reader}"},
    )
    assert r.status_code == 200, r.text
    assert r.json() == []


def test_scoped_token_rejects_missing_write_scope(client: TestClient) -> None:
    _login_admin(client)
    r = client.post(
        "/v1/boards",
        json={
            "name": "Scope Test",
            "columns": [{"name": "Intake", "order": 0}],
        },
    )
    assert r.status_code == 201, r.text
    board = r.json()
    first_column_id = board["columns"][0]["id"]
    token = client.post(
        "/v1/auth/tokens",
        json={"name": "readonly", "scopes": ["boards:read"]},
    ).json()["token"]
    client.post("/v1/auth/logout")

    r = client.post(
        "/v1/targets",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "board_id": board["id"],
            "column_id": first_column_id,
            "name": "Denied scoped write",
            "cot_type": "a-f-G-U-C",
            "lat": 30.0,
            "lon": -97.0,
            "time": datetime.now(tz=UTC).isoformat(),
        },
    )
    assert r.status_code == 403, r.text
    assert (
        r.json()["detail"]
        == f"missing required token scope: targets:write or targets:write:board:{board['id']}"
    )


def test_board_scoped_target_write_token_is_limited_to_that_board(
    client: TestClient,
) -> None:
    _login_admin(client)
    boards = []
    for name in ("Allowed Board", "Denied Board"):
        r = client.post(
            "/v1/boards",
            json={
                "name": name,
                "columns": [{"name": "Intake", "order": 0}],
            },
        )
        assert r.status_code == 201, r.text
        boards.append(r.json())
    allowed, denied = boards
    token = client.post(
        "/v1/auth/tokens",
        json={
            "name": "board-writer",
            "scopes": [f"targets:write:board:{allowed['id']}"],
        },
    ).json()["token"]
    client.post("/v1/auth/logout")

    r = client.post(
        "/v1/targets",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "board_id": allowed["id"],
            "column_id": allowed["columns"][0]["id"],
            "name": "Allowed scoped write",
            "cot_type": "a-f-G-U-C",
            "lat": 30.0,
            "lon": -97.0,
            "time": datetime.now(tz=UTC).isoformat(),
        },
    )
    assert r.status_code == 201, r.text

    r = client.post(
        "/v1/targets",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "board_id": denied["id"],
            "column_id": denied["columns"][0]["id"],
            "name": "Denied scoped write",
            "cot_type": "a-f-G-U-C",
            "lat": 30.0,
            "lon": -97.0,
            "time": datetime.now(tz=UTC).isoformat(),
        },
    )
    assert r.status_code == 403, r.text
    assert (
        r.json()["detail"]
        == f"missing required token scope: targets:write or targets:write:board:{denied['id']}"
    )


def test_board_scoped_target_read_token_is_limited_to_that_board(
    client: TestClient,
) -> None:
    _login_admin(client)
    boards = []
    targets = []
    for name in ("Allowed Read Board", "Denied Read Board"):
        r = client.post(
            "/v1/boards",
            json={
                "name": name,
                "columns": [{"name": "Intake", "order": 0}],
            },
        )
        assert r.status_code == 201, r.text
        board = r.json()
        boards.append(board)
        r = client.post(
            "/v1/targets",
            json={
                "board_id": board["id"],
                "column_id": board["columns"][0]["id"],
                "name": f"{name} Target",
                "cot_type": "a-f-G-U-C",
                "lat": 30.0,
                "lon": -97.0,
                "time": datetime.now(tz=UTC).isoformat(),
            },
        )
        assert r.status_code == 201, r.text
        targets.append(r.json())
    allowed, denied = boards
    allowed_target, denied_target = targets
    token = client.post(
        "/v1/auth/tokens",
        json={
            "name": "board-reader",
            "scopes": [f"targets:read:board:{allowed['id']}"],
        },
    ).json()["token"]
    client.post("/v1/auth/logout")

    r = client.get(
        f"/v1/targets?board_id={allowed['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    assert [target["id"] for target in r.json()] == [allowed_target["id"]]

    r = client.get(
        f"/v1/targets/{allowed_target['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["id"] == allowed_target["id"]

    r = client.get(
        f"/v1/targets?board_id={denied['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403, r.text
    assert (
        r.json()["detail"]
        == f"missing required token scope: targets:read or targets:read:board:{denied['id']}"
    )

    r = client.get(
        f"/v1/targets/{denied_target['id']}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403, r.text
    assert (
        r.json()["detail"]
        == f"missing required token scope: targets:read or targets:read:board:{denied['id']}"
    )


def test_board_scoped_target_read_token_controls_auxiliary_reads(
    client: TestClient,
) -> None:
    _login_admin(client)
    boards = []
    targets = []
    for name in ("Allowed Aux Read Board", "Denied Aux Read Board"):
        r = client.post(
            "/v1/boards",
            json={
                "name": name,
                "columns": [{"name": "Intake", "order": 0}],
            },
        )
        assert r.status_code == 201, r.text
        board = r.json()
        boards.append(board)
        r = client.post(
            "/v1/targets",
            json={
                "board_id": board["id"],
                "column_id": board["columns"][0]["id"],
                "name": f"{name} Target",
                "cot_type": "a-f-G-U-C",
                "lat": 30.0,
                "lon": -97.0,
                "time": datetime.now(tz=UTC).isoformat(),
            },
        )
        assert r.status_code == 201, r.text
        targets.append(r.json())
    allowed, denied = boards
    allowed_target, denied_target = targets
    token = client.post(
        "/v1/auth/tokens",
        json={
            "name": "board-aux-reader",
            "scopes": [f"targets:read:board:{allowed['id']}"],
        },
    ).json()["token"]
    client.post("/v1/auth/logout")
    headers = {"Authorization": f"Bearer {token}"}

    for suffix in ("eta", "observations"):
        r = client.get(f"/v1/targets/{allowed_target['id']}/{suffix}", headers=headers)
        assert r.status_code == 200, r.text

        r = client.get(f"/v1/targets/{denied_target['id']}/{suffix}", headers=headers)
        assert r.status_code == 403, r.text
        assert (
            r.json()["detail"]
            == f"missing required token scope: targets:read or targets:read:board:{denied['id']}"
        )


def test_board_scoped_target_tokens_control_workflow_routes(client: TestClient) -> None:
    _login_admin(client)
    board = client.post(
        "/v1/boards",
        json={
            "name": "Workflow Target Scope Board",
            "columns": [
                {"name": "Find", "order": 0},
                {"name": "Fix", "order": 1},
            ],
        },
    ).json()
    find_col, fix_col = board["columns"]
    target = client.post(
        "/v1/targets",
        json={
            "board_id": board["id"],
            "column_id": find_col["id"],
            "name": "WF-SCOPE",
            "lat": 33.0,
            "lon": -112.0,
            "time": datetime.now(tz=UTC).isoformat(),
        },
    ).json()
    denied = client.post(
        "/v1/auth/tokens",
        json={"name": "boards-only", "scopes": ["boards:read"]},
    ).json()["token"]
    reader = client.post(
        "/v1/auth/tokens",
        json={
            "name": "target-reader",
            "scopes": [f"targets:read:board:{board['id']}"],
        },
    ).json()["token"]
    writer = client.post(
        "/v1/auth/tokens",
        json={
            "name": "target-writer",
            "scopes": [f"targets:write:board:{board['id']}"],
        },
    ).json()["token"]
    nomination_to_approve = _insert_pending_nomination(
        target_id=target["id"],
        from_column_id=find_col["id"],
        to_column_id=fix_col["id"],
    )
    nomination_to_reject = _insert_pending_nomination(
        target_id=target["id"],
        from_column_id=find_col["id"],
        to_column_id=fix_col["id"],
    )
    client.post("/v1/auth/logout")

    denied_headers = {"Authorization": f"Bearer {denied}"}
    r = client.post(
        f"/v1/targets/{target['id']}/move/preview",
        headers=denied_headers,
        json={"column_id": fix_col["id"], "justification": "preview denied"},
    )
    assert r.status_code == 403, r.text
    assert (
        r.json()["detail"]
        == f"missing required token scope: targets:read or targets:read:board:{board['id']}"
    )

    for path in (
        f"/v1/targets/nominations/{nomination_to_approve}/approve",
        f"/v1/targets/nominations/{nomination_to_reject}/reject",
    ):
        r = client.post(
            path,
            headers=denied_headers,
            json={"justification": "denied"},
        )
        assert r.status_code == 403, r.text
        assert (
            r.json()["detail"]
            == f"missing required token scope: targets:write or targets:write:board:{board['id']}"
        )

    r = client.post(
        f"/v1/targets/{target['id']}/move/preview",
        headers={"Authorization": f"Bearer {reader}"},
        json={"column_id": fix_col["id"], "justification": "preview allowed"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["verdict"] == "allow"

    r = client.post(
        f"/v1/targets/nominations/{nomination_to_reject}/reject",
        headers={"Authorization": f"Bearer {writer}"},
        json={"justification": "bad match"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "rejected"


def test_board_scoped_target_write_token_can_patch_only_that_board(
    client: TestClient,
) -> None:
    _login_admin(client)
    boards = []
    targets = []
    for name in ("Allowed Patch Board", "Denied Patch Board"):
        r = client.post(
            "/v1/boards",
            json={
                "name": name,
                "columns": [{"name": "Intake", "order": 0}],
            },
        )
        assert r.status_code == 201, r.text
        board = r.json()
        boards.append(board)
        r = client.post(
            "/v1/targets",
            json={
                "board_id": board["id"],
                "column_id": board["columns"][0]["id"],
                "name": f"{name} Target",
                "cot_type": "a-f-G-U-C",
                "lat": 30.0,
                "lon": -97.0,
                "time": datetime.now(tz=UTC).isoformat(),
            },
        )
        assert r.status_code == 201, r.text
        targets.append(r.json())
    allowed, denied = boards
    allowed_target, denied_target = targets
    token = client.post(
        "/v1/auth/tokens",
        json={
            "name": "board-writer",
            "scopes": [f"targets:write:board:{allowed['id']}"],
        },
    ).json()["token"]
    client.post("/v1/auth/logout")

    r = client.patch(
        f"/v1/targets/{allowed_target['id']}",
        headers={"Authorization": f"Bearer {token}"},
        json={"remarks": "allowed edit"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["remarks"] == "allowed edit"

    r = client.patch(
        f"/v1/targets/{denied_target['id']}",
        headers={"Authorization": f"Bearer {token}"},
        json={"remarks": "denied edit"},
    )
    assert r.status_code == 403, r.text
    assert (
        r.json()["detail"]
        == f"missing required token scope: targets:write or targets:write:board:{denied['id']}"
    )


def test_board_scoped_target_write_token_can_move_only_that_board(
    client: TestClient,
) -> None:
    _login_admin(client)
    boards = []
    targets = []
    for name in ("Allowed Move Board", "Denied Move Board"):
        r = client.post(
            "/v1/boards",
            json={
                "name": name,
                "columns": [
                    {"name": "Intake", "order": 0},
                    {"name": "Done", "order": 1},
                ],
            },
        )
        assert r.status_code == 201, r.text
        board = r.json()
        boards.append(board)
        r = client.post(
            "/v1/targets",
            json={
                "board_id": board["id"],
                "column_id": board["columns"][0]["id"],
                "name": f"{name} Target",
                "cot_type": "a-f-G-U-C",
                "lat": 30.0,
                "lon": -97.0,
                "time": datetime.now(tz=UTC).isoformat(),
            },
        )
        assert r.status_code == 201, r.text
        targets.append(r.json())
    allowed, denied = boards
    allowed_target, denied_target = targets
    token = client.post(
        "/v1/auth/tokens",
        json={
            "name": "board-mover",
            "scopes": [f"targets:write:board:{allowed['id']}"],
        },
    ).json()["token"]
    client.post("/v1/auth/logout")

    r = client.post(
        f"/v1/targets/{allowed_target['id']}/move",
        headers={"Authorization": f"Bearer {token}"},
        json={"column_id": allowed["columns"][1]["id"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["id"] == allowed_target["id"]

    r = client.post(
        f"/v1/targets/{denied_target['id']}/move",
        headers={"Authorization": f"Bearer {token}"},
        json={"column_id": denied["columns"][1]["id"]},
    )
    assert r.status_code == 403, r.text
    assert (
        r.json()["detail"]
        == f"missing required token scope: targets:write or targets:write:board:{denied['id']}"
    )


def test_board_scoped_target_write_token_can_reorder_only_that_board(
    client: TestClient,
) -> None:
    _login_admin(client)
    boards = []
    targets = []
    for name in ("Allowed Reorder Board", "Denied Reorder Board"):
        r = client.post(
            "/v1/boards",
            json={
                "name": name,
                "columns": [{"name": "Intake", "order": 0}],
            },
        )
        assert r.status_code == 201, r.text
        board = r.json()
        boards.append(board)
        board_targets = []
        for index, target_name in enumerate(("First", "Second")):
            r = client.post(
                "/v1/targets",
                json={
                    "board_id": board["id"],
                    "column_id": board["columns"][0]["id"],
                    "name": f"{name} {target_name}",
                    "cot_type": "a-f-G-U-C",
                    "lat": 30.0 + index,
                    "lon": -97.0 - index,
                    "time": datetime.now(tz=UTC).isoformat(),
                },
            )
            assert r.status_code == 201, r.text
            board_targets.append(r.json())
        targets.append(board_targets)
    allowed, denied = boards
    allowed_targets, denied_targets = targets
    token = client.post(
        "/v1/auth/tokens",
        json={
            "name": "board-reorder",
            "scopes": [f"targets:write:board:{allowed['id']}"],
        },
    ).json()["token"]
    client.post("/v1/auth/logout")

    r = client.post(
        f"/v1/targets/{allowed_targets[1]['id']}/reorder",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "column_id": allowed["columns"][0]["id"],
            "after_id": allowed_targets[0]["id"],
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["id"] == allowed_targets[1]["id"]

    r = client.post(
        f"/v1/targets/{denied_targets[1]['id']}/reorder",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "column_id": denied["columns"][0]["id"],
            "after_id": denied_targets[0]["id"],
        },
    )
    assert r.status_code == 403, r.text
    assert (
        r.json()["detail"]
        == f"missing required token scope: targets:write or targets:write:board:{denied['id']}"
    )


def test_board_scoped_target_write_token_controls_auxiliary_mutations(
    client: TestClient,
) -> None:
    _login_admin(client)
    boards = []
    targets = []
    for name in ("Allowed Aux Board", "Denied Aux Board"):
        r = client.post(
            "/v1/boards",
            json={
                "name": name,
                "columns": [{"name": "Intake", "order": 0}],
            },
        )
        assert r.status_code == 201, r.text
        board = r.json()
        boards.append(board)
        r = client.post(
            "/v1/targets",
            json={
                "board_id": board["id"],
                "column_id": board["columns"][0]["id"],
                "name": f"{name} Target",
                "cot_type": "a-f-G-U-C",
                "lat": 30.0,
                "lon": -97.0,
                "time": datetime.now(tz=UTC).isoformat(),
            },
        )
        assert r.status_code == 201, r.text
        targets.append(r.json())
    allowed, denied = boards
    allowed_target, denied_target = targets
    token = client.post(
        "/v1/auth/tokens",
        json={
            "name": "board-aux",
            "scopes": [f"targets:write:board:{allowed['id']}"],
        },
    ).json()["token"]
    client.post("/v1/auth/logout")
    headers = {"Authorization": f"Bearer {token}"}

    r = client.post(
        f"/v1/targets/{allowed_target['id']}/assign",
        headers=headers,
        json={"callsign": "Alpha"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["assigned_callsigns"] == ["Alpha"]

    r = client.post(
        f"/v1/targets/{allowed_target['id']}/unassign",
        headers=headers,
        json={"callsign": "Alpha"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["assigned_callsigns"] == []

    r = client.post(
        f"/v1/targets/{allowed_target['id']}/attachments",
        headers=headers,
        json={
            "kind": "image",
            "url": "/captures/allowed.jpg",
            "sha256": "a" * 64,
            "media_type": "image/jpeg",
            "caption": "allowed",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["custom_fields"]["attachments"][0]["url"] == "/captures/allowed.jpg"

    r = client.delete(
        f"/v1/targets/{allowed_target['id']}/attachments/0",
        headers=headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["custom_fields"]["attachments"] == []

    r = client.post(
        f"/v1/targets/{allowed_target['id']}/damage-assessment",
        headers=headers,
        json={
            "address": "142 Oak St",
            "structure_type": "residential",
            "occupancy": "occupied",
            "damage_tier": "major",
            "owner_contact": None,
            "photo_refs": None,
            "notes": None,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["custom_fields"]["damage_assessment"]["damage_tier"] == "major"

    denied_requests = [
        (
            "post",
            f"/v1/targets/{denied_target['id']}/assign",
            {"callsign": "Bravo"},
        ),
        (
            "post",
            f"/v1/targets/{denied_target['id']}/unassign",
            {"callsign": "Bravo"},
        ),
        (
            "post",
            f"/v1/targets/{denied_target['id']}/attachments",
            {
                "kind": "image",
                "url": "/captures/denied.jpg",
                "sha256": "b" * 64,
                "media_type": "image/jpeg",
                "caption": "denied",
            },
        ),
        (
            "delete",
            f"/v1/targets/{denied_target['id']}/attachments/0",
            None,
        ),
        (
            "post",
            f"/v1/targets/{denied_target['id']}/damage-assessment",
            {
                "address": "143 Oak St",
                "structure_type": "residential",
                "occupancy": "occupied",
                "damage_tier": "minor",
                "owner_contact": None,
                "photo_refs": None,
                "notes": None,
            },
        ),
    ]
    for method, path, json_body in denied_requests:
        request = getattr(client, method)
        kwargs: dict[str, object] = {"headers": headers}
        if json_body is not None:
            kwargs["json"] = json_body
        r = request(path, **kwargs)
        assert r.status_code == 403, r.text
        assert (
            r.json()["detail"]
            == f"missing required token scope: targets:write or targets:write:board:{denied['id']}"
        )


def test_scoped_token_cannot_mint_more_tokens_without_token_write_scope(
    client: TestClient,
) -> None:
    _login_admin(client)
    token = client.post(
        "/v1/auth/tokens",
        json={"name": "readonly", "scopes": ["boards:read"]},
    ).json()["token"]
    client.post("/v1/auth/logout")

    r = client.post(
        "/v1/auth/tokens",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "escalation", "scopes": ["*"]},
    )

    assert r.status_code == 403, r.text
    assert r.json()["detail"] == "missing required token scope: tokens:write"


def test_audit_scope_gates_audit_log(client: TestClient) -> None:
    _login_admin(client)
    allowed = client.post(
        "/v1/auth/tokens",
        json={"name": "audit", "scopes": ["audit:read"]},
    ).json()["token"]
    denied = client.post(
        "/v1/auth/tokens",
        json={"name": "boards", "scopes": ["boards:read"]},
    ).json()["token"]
    client.post("/v1/auth/logout")

    r = client.get("/v1/audit", headers={"Authorization": f"Bearer {allowed}"})
    assert r.status_code == 200, r.text

    r = client.get("/v1/audit", headers={"Authorization": f"Bearer {denied}"})
    assert r.status_code == 403, r.text
    assert r.json()["detail"] == "missing required token scope: audit:read"


def test_user_scope_gates_user_directory(client: TestClient) -> None:
    _login_admin(client)
    allowed = client.post(
        "/v1/auth/tokens",
        json={"name": "users", "scopes": ["users:read"]},
    ).json()["token"]
    denied = client.post(
        "/v1/auth/tokens",
        json={"name": "boards", "scopes": ["boards:read"]},
    ).json()["token"]
    client.post("/v1/auth/logout")

    r = client.get("/v1/users", headers={"Authorization": f"Bearer {allowed}"})
    assert r.status_code == 200, r.text

    r = client.get("/v1/users", headers={"Authorization": f"Bearer {denied}"})
    assert r.status_code == 403, r.text
    assert r.json()["detail"] == "missing required token scope: users:read"


def test_resource_scopes_gate_roster_read_and_write(client: TestClient) -> None:
    _login_admin(client)
    reader = client.post(
        "/v1/auth/tokens",
        json={"name": "resource-reader", "scopes": ["resources:read"]},
    ).json()["token"]
    writer = client.post(
        "/v1/auth/tokens",
        json={"name": "resource-writer", "scopes": ["resources:write"]},
    ).json()["token"]
    client.post("/v1/auth/logout")

    r = client.get("/v1/resources", headers={"Authorization": f"Bearer {reader}"})
    assert r.status_code == 200, r.text

    r = client.post(
        "/v1/resources",
        headers={"Authorization": f"Bearer {reader}"},
        json={"callsign": "E-1", "name": "Engine 1"},
    )
    assert r.status_code == 403, r.text
    assert r.json()["detail"] == "missing required token scope: resources:write"

    r = client.post(
        "/v1/resources",
        headers={"Authorization": f"Bearer {writer}"},
        json={"callsign": "E-1", "name": "Engine 1"},
    )
    assert r.status_code == 201, r.text


def test_revoked_token_rejected(client: TestClient) -> None:
    _login_admin(client)
    body = client.post("/v1/auth/tokens", json={"name": "ci"}).json()
    token_id = body["id"]
    token = body["token"]
    r = client.delete(f"/v1/auth/tokens/{token_id}")
    assert r.status_code == 204
    client.post("/v1/auth/logout")
    r = client.get("/v1/boards", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401, r.text


def test_expired_token_rejected(client: TestClient) -> None:
    _login_admin(client)
    past = (datetime.now(tz=UTC) - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    token = client.post(
        "/v1/auth/tokens",
        json={"name": "expired", "expires_at": past},
    ).json()["token"]
    client.post("/v1/auth/logout")
    r = client.get("/v1/boards", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401, r.text


def test_create_token_requires_auth(client: TestClient) -> None:
    r = client.post("/v1/auth/tokens", json={"name": "anon"})
    assert r.status_code == 401
