"""Tests for the pure workflow trigger policy module."""

from __future__ import annotations

from uuid import UUID

from target_workspace.workflow.triggers import (
    WorkflowTriggerRule,
    presence_decisions,
)


def test_presence_decisions_returns_propose_decision_for_matching_rule() -> None:
    target_id = UUID("00000000-0000-0000-0000-000000000001")
    to_column_id = UUID("00000000-0000-0000-0000-000000000002")
    rule = WorkflowTriggerRule(
        id="rule-1",
        board_id="board-1",
        trigger="presence.arrived",
        condition="any",
        action_move_to_column_id=str(to_column_id),
        justification_template="{callsign} arrived",
    )

    decisions = presence_decisions(
        rules=[rule],
        event="presence.arrived",
        target_board_id="board-1",
        target_column_id="00000000-0000-0000-0000-000000000003",
        target_id=target_id,
        callsign="MEDIC-1",
        assigned_callsigns=["MEDIC-1"],
    )

    assert len(decisions) == 1
    assert decisions[0].verdict == "propose"
    assert decisions[0].target_id == target_id
    assert decisions[0].to_column_id == to_column_id
