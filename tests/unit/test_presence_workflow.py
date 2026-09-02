"""Tests for presence ingestion into workflow decisions."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from target_workspace.db import create_engine_for_url, create_tables, get_session
from target_workspace.db.repositories import create_board, create_target, create_workspace
from target_workspace.db.tables import (
    TargetTable,
    UserTable,
    WorkflowNominationTable,
    WorkflowTriggerTable,
)
from target_workspace.models.board import Board, Column
from target_workspace.models.target import Target
from target_workspace.workflow.presence import evaluate_presence_workflows

pytestmark = [pytest.mark.fast]


def test_evaluate_presence_workflows_creates_nomination_for_arrival() -> None:
    engine = create_engine_for_url("sqlite:///:memory:")
    create_tables(engine)
    try:
        with get_session(engine) as session:
            workspace = create_workspace(session, name="WS")
            user = UserTable(
                workspace_id=workspace.id,
                email="admin@example.com",
                display_name="Admin",
                role="admin",
                password_hash="x",
                created_at=datetime.now(tz=UTC),
            )
            session.add(user)
            session.flush()
            board = Board(
                name="SAR",
                columns=[
                    Column(name="Assigned", order=0),
                    Column(name="On-scene", order=1),
                ],
            )
            create_board(session, workspace.id, board)
            target = Target(
                name="Rescue 12",
                lat=35.60000,
                lon=-82.55000,
                time=datetime(2026, 6, 5, 2, 0, tzinfo=UTC),
                assigned_callsigns=["MEDIC-1"],
            )
            create_target(session, workspace.id, board.id, board.columns[0].id, target)
            target_row = session.get(TargetTable, target.id)
            assert target_row is not None
            target_row.assigned_callsigns = ["MEDIC-1"]
            session.add(target_row)
            rule = WorkflowTriggerTable(
                board_id=board.id,
                trigger="presence.arrived",
                condition="min_assignees:1",
                action_move_to_column_id=board.columns[1].id,
                justification_template="{callsign} arrived",
            )
            session.add(rule)
            session.flush()

            result = evaluate_presence_workflows(
                session,
                workspace_id=workspace.id,
                actor_id=user.id,
                callsign="MEDIC-1",
                lat=35.60001,
                lon=-82.55000,
                ce=10.0,
                source="unit-test",
            )
            nomination = session.get(WorkflowNominationTable, result.outcomes[0].nomination_id)

        assert result.outcomes[0].verdict == "propose"
        assert result.transitions[0]["event"] == "presence.arrived"
        assert nomination is not None
        assert nomination.to_column_id == board.columns[1].id
        assert nomination.evidence_json["geo_attestation"]["source"] == "unit-test"
    finally:
        engine.dispose()
