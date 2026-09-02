"""Tests for the workflow engine (TDD chunks 7+8)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from target_workspace.contracts.promotion_policy import Decision
from target_workspace.db import create_engine_for_url, create_tables, get_session
from target_workspace.db.repositories import (
    create_board,
    create_target,
    create_workspace,
)
from target_workspace.db.tables import (
    AuditEventTable,
    PublisherConfigTable,
    TargetTable,
    UserTable,
    WorkflowNominationTable,
    WorkflowTriggerTable,
)
from target_workspace.models.board import Board, Column
from target_workspace.models.target import Target
from target_workspace.workflow import (
    MoveRequested,
    PolicyDecisionContext,
    PresenceObserved,
    PromotionDenied,
    WorkflowContext,
    apply_decision,
    approve_nomination,
    evaluate,
    reduce_decisions,
    reject_nomination,
    transition_target,
)

pytestmark = [pytest.mark.fast]


@pytest.fixture
def engine() -> Iterator[Any]:
    eng = create_engine_for_url("sqlite:///:memory:")
    create_tables(eng)
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture
def context(engine: Any) -> dict[str, Any]:
    """Set up a workspace + admin user + F3EAD board + initial Target in FIND."""
    with get_session(engine) as session:
        ws = create_workspace(session, name="WS")
        user = UserTable(
            workspace_id=ws.id,
            email="a@example.com",
            display_name="A",
            role="admin",
            password_hash="x",
            created_at=datetime.now(tz=UTC),
        )
        session.add(user)
        session.flush()
        board = Board(
            name="F3EAD",
            columns=[
                Column(name="FIND", order=0),
                Column(name="FIX", order=1),
                Column(name="FINISH", order=2, requires_approval=True),
            ],
        )
        create_board(session, ws.id, board)
        target = Target(
            name="BISON-01",
            lat=33.4484,
            lon=-112.0740,
            time=datetime(2026, 5, 16, 21, 45, 0, tzinfo=UTC),
        )
        create_target(session, ws.id, board.id, board.columns[0].id, target)
        return {
            "engine": engine,
            "workspace_id": ws.id,
            "user_id": user.id,
            "board": board,
            "target_id": target.id,
        }


def _last_audit(engine: Any, target_id: Any) -> AuditEventTable | None:
    with get_session(engine) as session:
        rows = session.exec(
            __import__("sqlmodel")
            .select(AuditEventTable)
            .where(AuditEventTable.target_id == target_id)
            .order_by(AuditEventTable.occurred_at.desc())  # type: ignore[attr-defined]
        ).all()
        return rows[0] if rows else None


def test_legal_transition_persists_and_audits(context: dict[str, Any]) -> None:
    with get_session(context["engine"]) as session:
        result = transition_target(
            session,
            target_id=context["target_id"],
            to_column_id=context["board"].columns[1].id,  # FIX
            actor_id=context["user_id"],
            justification="cross-cue confirmed",
        )
    assert result.target.version == 2
    last = _last_audit(context["engine"], context["target_id"])
    assert last is not None
    assert last.event_type == "transitioned"
    assert last.justification == "cross-cue confirmed"


def test_evaluate_move_requested_is_pure_allow_decision(context: dict[str, Any]) -> None:
    with get_session(context["engine"]) as session:
        before = session.get(AuditEventTable, context["target_id"])
        target_before = session.get(TargetTable, context["target_id"])
        assert target_before is not None
        start_version = target_before.version
        signal = MoveRequested(
            target_id=context["target_id"],
            to_column_id=context["board"].columns[1].id,
            actor_id=context["user_id"],
            justification="cross-cue confirmed",
        )
        decision = evaluate(session, signal)
        target_after = session.get(TargetTable, context["target_id"])

    assert before is None
    assert target_after is not None
    assert target_after.version == start_version
    assert isinstance(decision, Decision)
    assert decision.verdict == "allow"
    assert decision.target_id == context["target_id"]
    assert decision.to_column_id == context["board"].columns[1].id


def test_apply_decision_is_the_manual_move_mutator(context: dict[str, Any]) -> None:
    with get_session(context["engine"]) as session:
        signal = MoveRequested(
            target_id=context["target_id"],
            to_column_id=context["board"].columns[1].id,
            actor_id=context["user_id"],
            justification="cross-cue confirmed",
        )
        decision = evaluate(session, signal)
        result = apply_decision(session, WorkflowContext(signal=signal), decision)

    assert result.target.version == 2
    last = _last_audit(context["engine"], context["target_id"])
    assert last is not None
    assert last.event_type == "transitioned"
    assert last.justification == "cross-cue confirmed"


def test_apply_propose_decision_writes_nomination_without_moving(
    context: dict[str, Any],
) -> None:
    class ApprovalPolicy:
        name = "policy:presence"

        def evaluate(self, ctx: PolicyDecisionContext) -> Decision:
            assert isinstance(ctx.signal, MoveRequested)
            return Decision.propose(
                reason="presence needs supervisor approval",
                proposed_by=self.name,
                approver_role="supervisor",
                target_id=ctx.signal.target_id,
                to_column_id=ctx.signal.to_column_id,
                evidence={"callsign": "BISON-01"},
            )

    with get_session(context["engine"]) as session:
        signal = MoveRequested(
            target_id=context["target_id"],
            to_column_id=context["board"].columns[1].id,
            actor_id=context["user_id"],
            justification="presence arrived",
        )
        target_before = session.get(TargetTable, context["target_id"])
        assert target_before is not None

        decision = evaluate(session, signal, policies=[ApprovalPolicy()])
        result = apply_decision(session, WorkflowContext(signal=signal), decision)
        nomination = session.exec(
            __import__("sqlmodel")
            .select(WorkflowNominationTable)
            .where(WorkflowNominationTable.target_id == context["target_id"])
        ).one()
        target_after = session.get(TargetTable, context["target_id"])

    assert decision.verdict == "propose"
    assert result.nomination_id == nomination.id
    assert result.publishers_notified == []
    assert target_after is not None
    assert target_after.column_id == target_before.column_id
    assert target_after.version == target_before.version
    assert nomination.status == "pending"
    assert nomination.from_column_id == target_before.column_id
    assert nomination.to_column_id == context["board"].columns[1].id
    assert nomination.proposed_by == "policy:presence"
    assert nomination.approver_role == "supervisor"
    assert nomination.evidence_json == {"callsign": "BISON-01"}
    last = _last_audit(context["engine"], context["target_id"])
    assert last is not None
    assert last.event_type == "nominated"
    assert last.to_column_id == context["board"].columns[1].id
    assert last.metadata_json["nomination_id"] == str(nomination.id)


def _create_pending_nomination(context: dict[str, Any]) -> Any:
    with get_session(context["engine"]) as session:
        target = session.get(TargetTable, context["target_id"])
        assert target is not None
        nomination = WorkflowNominationTable(
            workspace_id=context["workspace_id"],
            target_id=context["target_id"],
            from_column_id=target.column_id,
            to_column_id=context["board"].columns[1].id,
            proposed_by="policy:presence",
            actor_id=context["user_id"],
            approver_role="supervisor",
            reason="presence arrived",
            evidence_json={"callsign": "BISON-01"},
            created_at=datetime.now(tz=UTC),
        )
        session.add(nomination)
        session.flush()
        return nomination.id


def test_approve_nomination_reenters_pipeline_and_moves_card(context: dict[str, Any]) -> None:
    nomination_id = _create_pending_nomination(context)

    with get_session(context["engine"]) as session:
        result = approve_nomination(
            session,
            nomination_id=nomination_id,
            actor_id=context["user_id"],
            justification="supervisor confirmed",
        )
        nomination = session.get(WorkflowNominationTable, nomination_id)
        target = session.get(TargetTable, context["target_id"])

    assert result.target.version == 2
    assert result.nomination_id == nomination_id
    assert nomination is not None
    assert nomination.status == "approved"
    assert nomination.resolved_by == context["user_id"]
    assert nomination.resolved_at is not None
    assert target is not None
    assert target.column_id == context["board"].columns[1].id
    assert target.version == 2


def test_reject_nomination_records_rejection_without_moving(context: dict[str, Any]) -> None:
    nomination_id = _create_pending_nomination(context)

    with get_session(context["engine"]) as session:
        event = reject_nomination(
            session,
            nomination_id=nomination_id,
            actor_id=context["user_id"],
            justification="bad geofence match",
        )
        nomination = session.get(WorkflowNominationTable, nomination_id)
        target = session.get(TargetTable, context["target_id"])

    assert event.event_type == "rejected"
    assert event.metadata["nomination_id"] == str(nomination_id)
    assert nomination is not None
    assert nomination.status == "rejected"
    assert nomination.resolved_by == context["user_id"]
    assert nomination.resolved_at is not None
    assert target is not None
    assert target.column_id == context["board"].columns[0].id
    assert target.version == 1


def test_reduce_decisions_precedence_and_order() -> None:
    target_id = uuid4()
    to_column_id = uuid4()
    decisions = [
        Decision.allow(
            reason="board allows",
            proposed_by="policy:board",
            target_id=target_id,
            to_column_id=to_column_id,
        ),
        Decision.propose(
            reason="needs supervisor",
            proposed_by="policy:presence",
            approver_role="supervisor",
            target_id=target_id,
            to_column_id=to_column_id,
        ),
        Decision.deny(
            reason="blocked by safety",
            proposed_by="policy:safety",
            target_id=target_id,
            to_column_id=to_column_id,
        ),
    ]

    reduced = reduce_decisions(decisions)

    assert reduced.verdict == "deny"
    assert reduced.reason == "blocked by safety"
    assert reduced.proposed_by == "policy:safety"


def test_reduce_decisions_preserves_first_winning_policy() -> None:
    target_id = uuid4()
    to_column_id = uuid4()
    decisions = [
        Decision.abstain(reason="not applicable", proposed_by="policy:first"),
        Decision.allow(
            reason="first allow",
            proposed_by="policy:board",
            target_id=target_id,
            to_column_id=to_column_id,
        ),
        Decision.allow(
            reason="second allow",
            proposed_by="policy:other",
            target_id=target_id,
            to_column_id=to_column_id,
        ),
    ]

    reduced = reduce_decisions(decisions)

    assert reduced.verdict == "allow"
    assert reduced.reason == "first allow"
    assert reduced.proposed_by == "policy:board"


def test_reduce_decisions_all_abstain_returns_abstain() -> None:
    reduced = reduce_decisions(
        [
            Decision.abstain(reason="not this target", proposed_by="policy:a"),
            Decision.abstain(reason="not this board", proposed_by="policy:b"),
        ]
    )

    assert reduced.verdict == "abstain"
    assert reduced.proposed_by == "workflow:reducer"


def test_reduce_decisions_denies_conflicting_destinations() -> None:
    target_id = uuid4()
    requested_column_id = uuid4()
    alternate_column_id = uuid4()

    reduced = reduce_decisions(
        [
            Decision.allow(
                reason="board allows requested move",
                proposed_by="workflow:board",
                target_id=target_id,
                to_column_id=requested_column_id,
            ),
            Decision.propose(
                reason="policy wants a different destination",
                proposed_by="policy:reroute",
                approver_role="supervisor",
                target_id=target_id,
                to_column_id=alternate_column_id,
            ),
        ]
    )

    assert reduced.verdict == "deny"
    assert reduced.proposed_by == "workflow:reducer"
    assert reduced.reason == "policy decisions conflict on target or destination"


def test_evaluate_runs_ordered_policy_set_without_mutating(context: dict[str, Any]) -> None:
    class SafetyPolicy:
        name = "policy:safety"

        def evaluate(self, ctx: PolicyDecisionContext) -> Decision:
            assert isinstance(ctx.signal, MoveRequested)
            return Decision.deny(
                reason="safety hold",
                proposed_by=self.name,
                target_id=ctx.signal.target_id,
                to_column_id=ctx.signal.to_column_id,
            )

    with get_session(context["engine"]) as session:
        target_before = session.get(TargetTable, context["target_id"])
        assert target_before is not None
        signal = MoveRequested(
            target_id=context["target_id"],
            to_column_id=context["board"].columns[1].id,
            actor_id=context["user_id"],
        )

        decision = evaluate(session, signal, policies=[SafetyPolicy()])
        target_after = session.get(TargetTable, context["target_id"])

    assert decision.verdict == "deny"
    assert decision.proposed_by == "policy:safety"
    assert target_after is not None
    assert target_after.version == target_before.version
    assert _last_audit(context["engine"], context["target_id"]) is None


def test_evaluate_presence_observed_loads_persisted_trigger_policy(
    context: dict[str, Any],
) -> None:
    with get_session(context["engine"]) as session:
        target_before = session.get(TargetTable, context["target_id"])
        assert target_before is not None
        rule = WorkflowTriggerTable(
            board_id=context["board"].id,
            trigger="presence.arrived",
            condition="min_assignees:1",
            action_move_to_column_id=context["board"].columns[1].id,
            justification_template="{callsign} arrived",
        )
        session.add(rule)
        session.flush()

        decision = evaluate(
            session,
            PresenceObserved(
                target_id=context["target_id"],
                actor_id=context["user_id"],
                event="presence.arrived",
                callsign="BISON-01",
                assigned_callsigns=["BISON-01"],
                geo_attestation={"lat": 33.4484, "lon": -112.0740},
            ),
        )
        target_after = session.get(TargetTable, context["target_id"])

    assert decision.verdict == "propose"
    assert decision.proposed_by == f"workflow:presence:{rule.id}"
    assert decision.reason == "BISON-01 arrived"
    assert decision.target_id == context["target_id"]
    assert decision.to_column_id == context["board"].columns[1].id
    assert decision.approver_role == "approver"
    assert decision.evidence == {
        "rule_id": str(rule.id),
        "event": "presence.arrived",
        "callsign": "BISON-01",
        "geo_attestation": {"lat": 33.4484, "lon": -112.0740},
    }
    assert target_after is not None
    assert target_after.version == target_before.version
    assert _last_audit(context["engine"], context["target_id"]) is None


def test_board_topology_gate_cannot_be_widened_by_policy(context: dict[str, Any]) -> None:
    class UnsafeAllowPolicy:
        name = "policy:unsafe"

        def evaluate(self, ctx: PolicyDecisionContext) -> Decision:
            assert isinstance(ctx.signal, MoveRequested)
            return Decision.allow(
                reason="unsafe override",
                proposed_by=self.name,
                target_id=ctx.signal.target_id,
                to_column_id=ctx.signal.to_column_id,
            )

    with get_session(context["engine"]) as session:
        unsafe_to_column_id = uuid4()
        signal = MoveRequested(
            target_id=context["target_id"],
            to_column_id=unsafe_to_column_id,
            actor_id=context["user_id"],
        )

        decision = evaluate(session, signal, policies=[UnsafeAllowPolicy()])

    assert decision.verdict == "deny"
    assert decision.proposed_by == "workflow:board"
    assert decision.reason == "transition not allowed by board rules"


def test_promotion_denied_when_no_target(context: dict[str, Any]) -> None:
    with get_session(context["engine"]) as session, pytest.raises(PromotionDenied):
        transition_target(
            session,
            target_id=uuid4(),
            to_column_id=context["board"].columns[1].id,
            actor_id=context["user_id"],
        )


def test_promotion_denied_when_column_not_on_board(context: dict[str, Any]) -> None:
    with get_session(context["engine"]) as session, pytest.raises(PromotionDenied):
        transition_target(
            session,
            target_id=context["target_id"],
            to_column_id=uuid4(),
            actor_id=context["user_id"],
        )


def test_promotion_denied_when_approval_required_and_not_supplied(
    context: dict[str, Any],
) -> None:
    # First move FIND -> FIX (no approval required)
    with get_session(context["engine"]) as session:
        transition_target(
            session,
            target_id=context["target_id"],
            to_column_id=context["board"].columns[1].id,
            actor_id=context["user_id"],
        )
    # Then attempt FIX -> FINISH without approving_role
    with get_session(context["engine"]) as session, pytest.raises(PromotionDenied):
        transition_target(
            session,
            target_id=context["target_id"],
            to_column_id=context["board"].columns[2].id,
            actor_id=context["user_id"],
        )


def test_approval_allows_gated_transition(context: dict[str, Any]) -> None:
    # FIND -> FIX
    with get_session(context["engine"]) as session:
        transition_target(
            session,
            target_id=context["target_id"],
            to_column_id=context["board"].columns[1].id,
            actor_id=context["user_id"],
        )
    # FIX -> FINISH with approving_role supplied
    with get_session(context["engine"]) as session:
        result = transition_target(
            session,
            target_id=context["target_id"],
            to_column_id=context["board"].columns[2].id,
            actor_id=context["user_id"],
            approving_role="supervisor",
        )
    assert result.target.version == 3


def test_publisher_dispatch_on_filtered_column(context: dict[str, Any]) -> None:
    """If a PublisherConfig column-filter contains the destination, dispatch fires."""
    dispatches: list[dict[str, Any]] = []

    def dispatcher(
        *,
        publisher_id: Any,
        plugin_type: str,
        adapter_config: dict[str, Any],
        target: Any,
    ) -> None:
        _ = adapter_config  # unused in this fake
        dispatches.append(
            {
                "publisher_id": publisher_id,
                "plugin_type": plugin_type,
                "target_id": target.id,
            }
        )

    with get_session(context["engine"]) as session:
        fix_col_id = context["board"].columns[1].id
        pub = PublisherConfigTable(
            workspace_id=context["workspace_id"],
            name="test-pub",
            plugin_type="raw_cot",
            enabled=True,
            adapter_config={"transport": "udp", "host": "127.0.0.1", "port": 0},
            column_filter_ids=[str(fix_col_id)],
        )
        session.add(pub)
        session.flush()
        result = transition_target(
            session,
            target_id=context["target_id"],
            to_column_id=fix_col_id,
            actor_id=context["user_id"],
            publisher_dispatch=dispatcher,
        )

    assert len(dispatches) == 1
    assert dispatches[0]["plugin_type"] == "raw_cot"
    assert len(result.publishers_notified) == 1
