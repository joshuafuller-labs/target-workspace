"""Workflow trigger rules (tw-5m91).

Per-board rules table:
  { trigger: 'presence.arrived' | 'presence.departed',
    condition: 'min_assignees:N' | 'all_assigned',
    action_move_to_column_id: UUID,
    justification_template: str }

On geofence transition for a target, the trigger engine queries the
board's rules and fires matching ones. When a rule fires:

  - Target moves to action_move_to_column_id (unless that column is
    approval-gated; in that case audit-only and the gate handles the
    rest)
  - Audit event 'workflow.trigger.fired' is appended with the PLI fix
    that triggered it

Endpoints:
  POST   /v1/boards/{board_id}/workflow-triggers
  GET    /v1/boards/{board_id}/workflow-triggers
  PATCH  /v1/workflow-triggers/{id}
  DELETE /v1/workflow-triggers/{id}
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.fast]


def _login(c: TestClient) -> None:
    r = c.post(
        "/v1/auth/login",
        json={"email": "admin@example.com", "password": "test-pw"},
    )
    assert r.status_code == 200, r.text


def _make_board(c: TestClient) -> dict[str, Any]:
    r = c.post(
        "/v1/boards",
        json={
            "name": "B",
            "columns": [
                {"name": "Assigned", "order": 0},
                {"name": "On-scene", "order": 1},
            ],
        },
    )
    assert r.status_code in (200, 201), r.text
    return r.json()


def test_create_workflow_trigger(client: TestClient) -> None:
    _login(client)
    b = _make_board(client)
    dest_col = b["columns"][1]["id"]
    r = client.post(
        f"/v1/boards/{b['id']}/workflow-triggers",
        json={
            "trigger": "presence.arrived",
            "condition": "min_assignees:1",
            "action_move_to_column_id": dest_col,
            "justification_template": "{callsign} arrived at target",
        },
    )
    assert r.status_code == 200, r.text
    rule = r.json()
    assert rule["trigger"] == "presence.arrived"
    assert rule["condition"] == "min_assignees:1"
    assert rule["action_move_to_column_id"] == dest_col


def test_list_workflow_triggers(client: TestClient) -> None:
    _login(client)
    b = _make_board(client)
    dest_col = b["columns"][1]["id"]
    for trig in ("presence.arrived", "presence.departed"):
        client.post(
            f"/v1/boards/{b['id']}/workflow-triggers",
            json={
                "trigger": trig,
                "condition": "min_assignees:1",
                "action_move_to_column_id": dest_col,
                "justification_template": "{callsign} {trigger}",
            },
        )
    r = client.get(f"/v1/boards/{b['id']}/workflow-triggers")
    assert r.status_code == 200, r.text
    rows = r.json()
    assert len(rows) == 2
    assert {r["trigger"] for r in rows} == {"presence.arrived", "presence.departed"}


def test_delete_workflow_trigger(client: TestClient) -> None:
    _login(client)
    b = _make_board(client)
    dest_col = b["columns"][1]["id"]
    rule = client.post(
        f"/v1/boards/{b['id']}/workflow-triggers",
        json={
            "trigger": "presence.arrived",
            "condition": "min_assignees:1",
            "action_move_to_column_id": dest_col,
            "justification_template": "x",
        },
    ).json()
    r = client.delete(f"/v1/workflow-triggers/{rule['id']}")
    assert r.status_code == 204
    rows = client.get(f"/v1/boards/{b['id']}/workflow-triggers").json()
    assert rows == []


def test_fire_workflow_triggers_returns_actions() -> None:
    """fire_workflow_triggers picks matching rules and returns concrete
    actions for the caller to apply."""
    from target_workspace.api.workflow_triggers import (
        WorkflowTriggerRule,
        consider_actions,
    )

    rule = WorkflowTriggerRule(
        id="rule-1",
        board_id="board-1",
        trigger="presence.arrived",
        condition="min_assignees:1",
        action_move_to_column_id="col-2",
        justification_template="{callsign} arrived",
    )
    actions = consider_actions(
        rules=[rule],
        event="presence.arrived",
        target_board_id="board-1",
        target_column_id="col-1",
        callsign="MEDIC-1",
        assigned_callsigns=["MEDIC-1"],
    )
    assert len(actions) == 1
    a = actions[0]
    assert a["rule_id"] == "rule-1"
    assert a["move_to_column_id"] == "col-2"
    assert "MEDIC-1" in a["justification"]


def test_presence_workflow_policy_returns_propose_decision() -> None:
    from uuid import UUID

    from target_workspace.api.workflow_triggers import (
        PresenceWorkflowPolicy,
        WorkflowTriggerRule,
    )

    target_id = UUID("00000000-0000-0000-0000-000000000001")
    to_column_id = UUID("00000000-0000-0000-0000-000000000002")
    rule = WorkflowTriggerRule(
        id="rule-1",
        board_id="board-1",
        trigger="presence.arrived",
        condition="min_assignees:1",
        action_move_to_column_id=str(to_column_id),
        justification_template="{callsign} arrived",
    )

    decision = PresenceWorkflowPolicy(
        rule=rule,
        event="presence.arrived",
        target_board_id="board-1",
        target_column_id="col-1",
        target_id=target_id,
        callsign="MEDIC-1",
        assigned_callsigns=["MEDIC-1"],
        geo_attestation={"lat": 35.6, "lon": -82.5},
    ).evaluate()

    assert decision.verdict == "propose"
    assert decision.proposed_by == "workflow:presence:rule-1"
    assert decision.target_id == target_id
    assert decision.to_column_id == to_column_id
    assert decision.approver_role == "approver"
    assert decision.reason == "MEDIC-1 arrived"
    assert decision.evidence == {
        "rule_id": "rule-1",
        "event": "presence.arrived",
        "callsign": "MEDIC-1",
        "geo_attestation": {"lat": 35.6, "lon": -82.5},
    }


def _make_trigger(c: TestClient, board_id: str, dest_col: str) -> dict[str, Any]:
    return c.post(
        f"/v1/boards/{board_id}/workflow-triggers",
        json={
            "trigger": "presence.arrived",
            "condition": "min_assignees:1",
            "action_move_to_column_id": dest_col,
            "justification_template": "x",
        },
    ).json()


def test_patch_workflow_trigger_updates_fields(client: TestClient) -> None:
    _login(client)
    b = _make_board(client)
    dest = b["columns"][1]["id"]
    rule = _make_trigger(client, b["id"], dest)
    r = client.patch(
        f"/v1/workflow-triggers/{rule['id']}",
        json={"trigger": "presence.departed", "condition": "all_assigned"},
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["trigger"] == "presence.departed"
    assert out["condition"] == "all_assigned"
    # Field not in the patch body is left unchanged.
    assert out["action_move_to_column_id"] == dest


def test_create_trigger_invalid_type_returns_422(client: TestClient) -> None:
    _login(client)
    b = _make_board(client)
    r = client.post(
        f"/v1/boards/{b['id']}/workflow-triggers",
        json={
            "trigger": "not-a-real-trigger",
            "condition": "all_assigned",
            "action_move_to_column_id": b["columns"][1]["id"],
            "justification_template": "x",
        },
    )
    assert r.status_code == 422, r.text


def test_create_trigger_unknown_board_returns_404(client: TestClient) -> None:
    _login(client)
    r = client.post(
        f"/v1/boards/{uuid4()}/workflow-triggers",
        json={
            "trigger": "presence.arrived",
            "condition": "all_assigned",
            "action_move_to_column_id": str(uuid4()),
            "justification_template": "x",
        },
    )
    assert r.status_code == 404, r.text


def test_patch_unknown_trigger_returns_404(client: TestClient) -> None:
    _login(client)
    r = client.patch(f"/v1/workflow-triggers/{uuid4()}", json={"condition": "all_assigned"})
    assert r.status_code == 404, r.text


def test_delete_unknown_trigger_returns_404(client: TestClient) -> None:
    _login(client)
    r = client.delete(f"/v1/workflow-triggers/{uuid4()}")
    assert r.status_code == 404, r.text


def test_patch_trigger_invalid_type_returns_422(client: TestClient) -> None:
    _login(client)
    b = _make_board(client)
    rule = _make_trigger(client, b["id"], b["columns"][1]["id"])
    r = client.patch(
        f"/v1/workflow-triggers/{rule['id']}",
        json={"trigger": "nope"},
    )
    assert r.status_code == 422, r.text


def test_fire_consider_skips_non_matching_event() -> None:
    from target_workspace.api.workflow_triggers import (
        WorkflowTriggerRule,
        consider_actions,
    )

    rule = WorkflowTriggerRule(
        id="r",
        board_id="b",
        trigger="presence.arrived",
        condition="min_assignees:1",
        action_move_to_column_id="col-2",
        justification_template="x",
    )
    actions = consider_actions(
        rules=[rule],
        event="presence.departed",
        target_board_id="b",
        target_column_id="col-1",
        callsign="X",
        assigned_callsigns=["X"],
    )
    assert actions == []


def test_fire_consider_respects_min_assignees() -> None:
    from target_workspace.api.workflow_triggers import (
        WorkflowTriggerRule,
        consider_actions,
    )

    rule = WorkflowTriggerRule(
        id="r",
        board_id="b",
        trigger="presence.arrived",
        condition="min_assignees:2",
        action_move_to_column_id="col-2",
        justification_template="x",
    )
    actions = consider_actions(
        rules=[rule],
        event="presence.arrived",
        target_board_id="b",
        target_column_id="col-1",
        callsign="A",
        assigned_callsigns=["A"],
    )
    assert actions == []
    actions2 = consider_actions(
        rules=[rule],
        event="presence.arrived",
        target_board_id="b",
        target_column_id="col-1",
        callsign="A",
        assigned_callsigns=["A", "B"],
    )
    assert len(actions2) == 1


def test_fire_consider_all_assigned_requires_full_arrival() -> None:
    """The 'all_assigned' condition needs every assigned callsign to
    have been observed arriving — modeled here via the
    callsigns_already_arrived parameter."""
    from target_workspace.api.workflow_triggers import (
        WorkflowTriggerRule,
        consider_actions,
    )

    rule = WorkflowTriggerRule(
        id="r",
        board_id="b",
        trigger="presence.arrived",
        condition="all_assigned",
        action_move_to_column_id="col-2",
        justification_template="x",
    )
    # Only one arrived so far — should not fire.
    actions = consider_actions(
        rules=[rule],
        event="presence.arrived",
        target_board_id="b",
        target_column_id="col-1",
        callsign="A",
        assigned_callsigns=["A", "B"],
        callsigns_already_arrived={"A"},
    )
    assert actions == []
    # Both arrived — should fire.
    actions2 = consider_actions(
        rules=[rule],
        event="presence.arrived",
        target_board_id="b",
        target_column_id="col-1",
        callsign="B",
        assigned_callsigns=["A", "B"],
        callsigns_already_arrived={"A", "B"},
    )
    assert len(actions2) == 1
