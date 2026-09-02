"""Workflow engine.

Per ADR 0008 the engine is data-driven — PromotionPolicy rows determine
behavior, not branching code. MVP enables `gated` mode; conditional and
autonomous land later behind the same surface.

This module owns three orchestrations:

- `transition_target(...)` — validates the column move against Board rules,
  enforces requires_approval if the destination column is gated, persists
  the move (version-bump), writes an AuditEvent, and dispatches any
  configured Publishers.
- `record_event(...)` — append-only audit write helper used by callers
  that don't need a transition.

The publisher dispatch is fire-and-forget for MVP (publishers are best-
effort and their failures don't block the transition). Per ADR 0010,
`now_utc()` lives in the repositories module so future demo-replay can
inject a controllable clock.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol
from uuid import UUID

from sqlmodel import Session, select

from target_workspace.contracts.promotion_policy import Decision
from target_workspace.db.repositories import (
    _row_to_target,
    move_target_to_column,
    now_utc,
)
from target_workspace.db.tables import (
    AuditEventTable,
    BoardTable,
    ColumnTable,
    PublisherConfigTable,
    TargetTable,
    WorkflowNominationTable,
    WorkflowTriggerTable,
)
from target_workspace.models.audit_event import AuditEvent, EventType
from target_workspace.models.board import Board, Column
from target_workspace.models.target import Target
from target_workspace.workflow.triggers import (
    PresenceWorkflowPolicy,
    WorkflowTriggerRule,
)


class PromotionDenied(Exception):
    """Raised when a transition is rejected by board rules or policy."""


@dataclass
class PromotionResult:
    target: Target
    event: AuditEvent
    publishers_notified: list[UUID]
    nomination_id: UUID | None = None


@dataclass(frozen=True)
class MoveRequested:
    target_id: UUID
    to_column_id: UUID
    actor_id: UUID
    justification: str | None = None
    approving_role: str | None = None


@dataclass(frozen=True)
class PresenceObserved:
    target_id: UUID
    actor_id: UUID
    event: str
    callsign: str
    assigned_callsigns: list[str]
    callsigns_already_arrived: set[str] | None = None
    geo_attestation: dict[str, Any] | None = None
    justification: str | None = None


type WorkflowSignal = MoveRequested | PresenceObserved


@dataclass(frozen=True)
class WorkflowContext:
    signal: WorkflowSignal
    publisher_dispatch: Any = None


@dataclass(frozen=True)
class PolicyDecisionContext:
    signal: WorkflowSignal
    target: TargetTable | None
    board: Board | None


class WorkflowPolicy(Protocol):
    name: str

    def evaluate(self, ctx: PolicyDecisionContext) -> Decision: ...


class BoardMovePolicy:
    name = "workflow:board"

    def evaluate(self, ctx: PolicyDecisionContext) -> Decision:
        signal = ctx.signal
        assert isinstance(signal, MoveRequested)
        if ctx.target is None:
            return Decision.deny(
                reason="target not found",
                proposed_by=self.name,
                target_id=signal.target_id,
                to_column_id=signal.to_column_id,
            )

        if ctx.board is None:
            return Decision.deny(
                reason="target's board not found",
                proposed_by=self.name,
                target_id=signal.target_id,
                to_column_id=signal.to_column_id,
            )

        if not ctx.board.can_move(ctx.target.column_id, signal.to_column_id):
            return Decision.deny(
                reason="transition not allowed by board rules",
                proposed_by=self.name,
                target_id=signal.target_id,
                to_column_id=signal.to_column_id,
            )

        to_column = next((c for c in ctx.board.columns if c.id == signal.to_column_id), None)
        if to_column is None:
            return Decision.deny(
                reason="to_column does not belong to the target's board",
                proposed_by=self.name,
                target_id=signal.target_id,
                to_column_id=signal.to_column_id,
            )

        if to_column.requires_approval and not signal.approving_role:
            return Decision.deny(
                reason="target column requires_approval; approving_role missing",
                proposed_by=self.name,
                target_id=signal.target_id,
                to_column_id=signal.to_column_id,
            )

        return Decision.allow(
            reason="manual move allowed",
            proposed_by=self.name,
            target_id=signal.target_id,
            to_column_id=signal.to_column_id,
            evidence={"from_column_id": str(ctx.target.column_id)},
        )


def reduce_decisions(decisions: list[Decision]) -> Decision:
    """Reduce ordered policy decisions by ADR 0021 precedence.

    Precedence is DENY > PROPOSE > ALLOW > ABSTAIN. Within the winning
    precedence tier, the first policy wins so board policy ordering remains
    meaningful.
    """
    decisive = [decision for decision in decisions if decision.verdict != "abstain"]
    target_ids = {decision.target_id for decision in decisive if decision.target_id is not None}
    to_column_ids = {
        decision.to_column_id for decision in decisive if decision.to_column_id is not None
    }
    if len(target_ids) > 1 or len(to_column_ids) > 1:
        return Decision.deny(
            reason="policy decisions conflict on target or destination",
            proposed_by="workflow:reducer",
            target_id=next(iter(target_ids)) if len(target_ids) == 1 else None,
            to_column_id=next(iter(to_column_ids)) if len(to_column_ids) == 1 else None,
            evidence={
                "decisions": [
                    {
                        "verdict": decision.verdict,
                        "proposed_by": decision.proposed_by,
                        "target_id": str(decision.target_id)
                        if decision.target_id is not None
                        else None,
                        "to_column_id": str(decision.to_column_id)
                        if decision.to_column_id is not None
                        else None,
                    }
                    for decision in decisive
                ]
            },
        )
    for verdict in ("deny", "propose", "allow"):
        for decision in decisions:
            if decision.verdict == verdict:
                return decision
    return Decision.abstain(
        reason="all policies abstained",
        proposed_by="workflow:reducer",
    )


def evaluate_policy_decisions(
    ctx: PolicyDecisionContext,
    policies: list[WorkflowPolicy] | None = None,
) -> list[Decision]:
    board_policies: list[WorkflowPolicy] = (
        [BoardMovePolicy()] if isinstance(ctx.signal, MoveRequested) else []
    )
    ordered_policies: list[WorkflowPolicy] = [*board_policies, *(policies or [])]
    return [policy.evaluate(ctx) for policy in ordered_policies]


class _PresenceTriggerPolicy:
    def __init__(
        self,
        *,
        rule: WorkflowTriggerRule,
        signal: PresenceObserved,
        target_column_id: UUID,
    ) -> None:
        self._delegate = PresenceWorkflowPolicy(
            rule=rule,
            event=signal.event,
            target_board_id=rule.board_id,
            target_column_id=str(target_column_id),
            target_id=signal.target_id,
            callsign=signal.callsign,
            assigned_callsigns=signal.assigned_callsigns,
            callsigns_already_arrived=signal.callsigns_already_arrived,
            geo_attestation=signal.geo_attestation,
        )
        self.name = self._delegate.name

    def evaluate(self, ctx: PolicyDecisionContext) -> Decision:
        _ = ctx
        return self._delegate.evaluate()


def _presence_trigger_policies(
    session: Session,
    signal: PresenceObserved,
    target_row: TargetTable | None,
) -> list[WorkflowPolicy]:
    if target_row is None:
        return []
    rows = session.exec(
        select(WorkflowTriggerTable).where(WorkflowTriggerTable.board_id == target_row.board_id)
    ).all()
    return [
        _PresenceTriggerPolicy(
            rule=WorkflowTriggerRule(
                id=str(row.id),
                board_id=str(row.board_id),
                trigger=row.trigger,
                condition=row.condition,
                action_move_to_column_id=str(row.action_move_to_column_id),
                justification_template=row.justification_template,
            ),
            signal=signal,
            target_column_id=target_row.column_id,
        )
        for row in rows
    ]


def _load_board(session: Session, board_id: UUID) -> Board | None:
    """Materialize a Board (with Columns) from the DB."""
    row = session.get(BoardTable, board_id)
    if row is None:
        return None
    cols = session.exec(select(ColumnTable).where(ColumnTable.board_id == board_id)).all()
    return Board(
        id=row.id,
        name=row.name,
        transitions=row.transitions,
        columns=[
            Column(
                id=c.id,
                name=c.name,
                order=c.order,
                wip_limit=c.wip_limit,
                color=c.color,
                requires_approval=c.requires_approval,
            )
            for c in cols
        ],
    )


def record_event(
    session: Session,
    *,
    workspace_id: UUID,
    target_id: UUID,
    actor_id: UUID,
    event_type: EventType,
    actor_kind: str | None = None,
    actor_ref: str | None = None,
    from_column_id: UUID | None = None,
    to_column_id: UUID | None = None,
    justification: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuditEvent:
    """Append an AuditEvent row and return the model."""
    from target_workspace.api.signing import sign_audit_event  # noqa: PLC0415

    row = AuditEventTable(
        workspace_id=workspace_id,
        target_id=target_id,
        actor_id=actor_id,
        actor_kind=actor_kind or "human_user",
        actor_ref=actor_ref,
        event_type=event_type,
        occurred_at=now_utc(),
        from_column_id=from_column_id,
        to_column_id=to_column_id,
        justification=justification,
        metadata_json=dict(metadata or {}),
    )
    session.add(row)
    session.flush()
    # tw-16c0: sign at insertion. Peer-id + signature are derived from the
    # local instance identity (bootstrapped on first call).
    peer_id, sig, prev_hash = sign_audit_event(
        session,
        event_id=row.id,
        workspace_id=row.workspace_id,
        actor_id=row.actor_id,
        event_type=row.event_type,
        target_id=row.target_id,
        occurred_at=row.occurred_at,
        metadata=row.metadata_json,
        actor_kind=row.actor_kind,
        actor_ref=row.actor_ref,
        signature_format_version=2 if row.actor_kind != "human_user" else 1,
    )
    row.signature_format_version = 2 if row.actor_kind != "human_user" else 1
    row.peer_id = peer_id
    row.prev_hash = prev_hash
    row.signature = sig
    session.add(row)
    session.flush()
    # tw-ngn5: fan out to registered triggers AFTER persistence.
    from target_workspace.api.triggers import (  # noqa: PLC0415
        EmittedAuditEvent,
        fan_out,
    )

    fan_out(
        EmittedAuditEvent(
            id=row.id,
            workspace_id=row.workspace_id,
            event_type=row.event_type,
            actor_id=row.actor_id,
            target_id=row.target_id,
            occurred_at=row.occurred_at,
            metadata=dict(row.metadata_json),
            peer_id=row.peer_id,
            signature=row.signature,
        )
    )
    return AuditEvent(
        id=row.id,
        target_id=row.target_id,
        actor_id=row.actor_id,
        event_type=event_type,
        occurred_at=row.occurred_at,
        from_column_id=row.from_column_id,
        to_column_id=row.to_column_id,
        justification=row.justification,
        metadata=dict(row.metadata_json),
    )


def evaluate(
    session: Session,
    signal: WorkflowSignal,
    *,
    policies: list[WorkflowPolicy] | None = None,
) -> Decision:
    """Purely decide whether a manual move is allowed.

    This function may read DB state but must not mutate rows or dispatch
    publishers. `apply_decision` owns side effects.
    """
    target_row = session.get(TargetTable, signal.target_id)
    board = _load_board(session, target_row.board_id) if target_row is not None else None
    ordered_policies = list(policies or [])
    if isinstance(signal, PresenceObserved):
        ordered_policies = [
            *_presence_trigger_policies(session, signal, target_row),
            *ordered_policies,
        ]
    return reduce_decisions(
        evaluate_policy_decisions(
            PolicyDecisionContext(signal=signal, target=target_row, board=board),
            ordered_policies,
        )
    )


def apply_decision(
    session: Session,
    ctx: WorkflowContext,
    decision: Decision,
) -> PromotionResult:
    """Apply an allowed decision. This is the mutation boundary."""
    if decision.verdict not in {"allow", "propose"}:
        raise PromotionDenied(decision.reason)
    signal = ctx.signal
    if decision.target_id != signal.target_id or decision.to_column_id is None:
        msg = "decision does not match signal"
        raise PromotionDenied(msg)
    if isinstance(signal, MoveRequested) and decision.to_column_id != signal.to_column_id:
        msg = "decision does not match signal"
        raise PromotionDenied(msg)
    to_column_id = decision.to_column_id

    target_row = session.get(TargetTable, signal.target_id)
    if target_row is None:
        msg = "target not found"
        raise PromotionDenied(msg)
    from_column_id = target_row.column_id

    if decision.verdict == "propose":
        if decision.approver_role is None:
            msg = "propose decisions require approver_role"
            raise PromotionDenied(msg)
        nomination = WorkflowNominationTable(
            workspace_id=target_row.workspace_id,
            target_id=signal.target_id,
            from_column_id=from_column_id,
            to_column_id=to_column_id,
            proposed_by=decision.proposed_by,
            actor_id=signal.actor_id,
            approver_role=decision.approver_role,
            reason=decision.reason,
            evidence_json=dict(decision.evidence),
            created_at=now_utc(),
        )
        session.add(nomination)
        session.flush()
        event = record_event(
            session,
            workspace_id=target_row.workspace_id,
            target_id=signal.target_id,
            actor_id=signal.actor_id,
            actor_kind="policy_agent",
            actor_ref=decision.proposed_by,
            event_type="nominated",
            from_column_id=from_column_id,
            to_column_id=to_column_id,
            justification=signal.justification,
            metadata={
                "nomination_id": str(nomination.id),
                "proposed_by": decision.proposed_by,
                "approver_role": decision.approver_role,
                "reason": decision.reason,
                "evidence": dict(decision.evidence),
            },
        )
        return PromotionResult(
            target=_row_to_target(target_row),
            event=event,
            publishers_notified=[],
            nomination_id=nomination.id,
        )

    moved_row = move_target_to_column(session, signal.target_id, to_column_id)
    assert moved_row is not None

    event = record_event(
        session,
        workspace_id=moved_row.workspace_id,
        target_id=signal.target_id,
        actor_id=signal.actor_id,
        actor_kind=(
            "human_user" if decision.proposed_by == BoardMovePolicy.name else "policy_agent"
        ),
        actor_ref=None if decision.proposed_by == BoardMovePolicy.name else decision.proposed_by,
        event_type="transitioned",
        from_column_id=from_column_id,
        to_column_id=to_column_id,
        justification=signal.justification,
        metadata=(
            {"approving_role": signal.approving_role}
            if isinstance(signal, MoveRequested) and signal.approving_role
            else None
        ),
    )

    publishers_notified: list[UUID] = []
    pubs = session.exec(
        select(PublisherConfigTable).where(
            PublisherConfigTable.workspace_id == moved_row.workspace_id,
            PublisherConfigTable.enabled == True,  # noqa: E712
        )
    ).all()
    to_column_id_str = str(to_column_id)
    for p in pubs:
        if to_column_id_str in p.column_filter_ids:
            publishers_notified.append(p.id)
            if ctx.publisher_dispatch is not None:
                cfg = dict(p.adapter_config)
                cfg.setdefault("board_id", str(moved_row.board_id))
                try:
                    ctx.publisher_dispatch(
                        publisher_id=p.id,
                        plugin_type=p.plugin_type,
                        adapter_config=cfg,
                        target=_row_to_target(moved_row),
                    )
                except Exception:
                    record_event(
                        session,
                        workspace_id=moved_row.workspace_id,
                        target_id=signal.target_id,
                        actor_id=signal.actor_id,
                        event_type="updated",
                        justification=f"publisher {p.name} dispatch failed",
                        metadata={"publisher_id": str(p.id)},
                    )

    return PromotionResult(
        target=_row_to_target(moved_row),
        event=event,
        publishers_notified=publishers_notified,
    )


def _load_pending_nomination(
    session: Session,
    nomination_id: UUID,
) -> WorkflowNominationTable:
    nomination = session.get(WorkflowNominationTable, nomination_id)
    if nomination is None:
        msg = "nomination not found"
        raise PromotionDenied(msg)
    if nomination.status != "pending":
        msg = f"nomination is {nomination.status}"
        raise PromotionDenied(msg)
    return nomination


def approve_nomination(
    session: Session,
    *,
    nomination_id: UUID,
    actor_id: UUID,
    justification: str | None = None,
    publisher_dispatch: Any = None,
) -> PromotionResult:
    """Approve a pending nomination by re-entering evaluate/apply."""
    nomination = _load_pending_nomination(session, nomination_id)
    signal = MoveRequested(
        target_id=nomination.target_id,
        to_column_id=nomination.to_column_id,
        actor_id=actor_id,
        justification=justification,
        approving_role=nomination.approver_role,
    )
    decision = evaluate(session, signal)
    result = apply_decision(
        session,
        WorkflowContext(signal=signal, publisher_dispatch=publisher_dispatch),
        decision,
    )
    nomination.status = "approved"
    nomination.resolved_at = now_utc()
    nomination.resolved_by = actor_id
    session.add(nomination)
    record_event(
        session,
        workspace_id=nomination.workspace_id,
        target_id=nomination.target_id,
        actor_id=actor_id,
        event_type="approved",
        from_column_id=nomination.from_column_id,
        to_column_id=nomination.to_column_id,
        justification=justification,
        metadata={"nomination_id": str(nomination.id)},
    )
    result.nomination_id = nomination.id
    return result


def reject_nomination(
    session: Session,
    *,
    nomination_id: UUID,
    actor_id: UUID,
    justification: str | None = None,
) -> AuditEvent:
    """Reject a pending nomination without moving the target."""
    nomination = _load_pending_nomination(session, nomination_id)
    nomination.status = "rejected"
    nomination.resolved_at = now_utc()
    nomination.resolved_by = actor_id
    session.add(nomination)
    return record_event(
        session,
        workspace_id=nomination.workspace_id,
        target_id=nomination.target_id,
        actor_id=actor_id,
        event_type="rejected",
        from_column_id=nomination.from_column_id,
        to_column_id=nomination.to_column_id,
        justification=justification,
        metadata={"nomination_id": str(nomination.id)},
    )


def transition_target(
    session: Session,
    *,
    target_id: UUID,
    to_column_id: UUID,
    actor_id: UUID,
    justification: str | None = None,
    approving_role: str | None = None,
    publisher_dispatch: Any = None,
) -> PromotionResult:
    """Validate + persist + audit a column move.

    Per ADR 0008, behavior is driven by Board rules + (future) PromotionPolicy.
    MVP enforces:
      - target exists
      - target's board contains both from_column and to_column
      - Board.can_move(from, to) accepts the transition
      - if to_column.requires_approval=True, `approving_role` must be set

    Returns the updated Target, the persisted AuditEvent, and any publisher IDs
    that were dispatched.
    """
    signal = MoveRequested(
        target_id=target_id,
        to_column_id=to_column_id,
        actor_id=actor_id,
        justification=justification,
        approving_role=approving_role,
    )
    decision = evaluate(session, signal)
    return apply_decision(
        session,
        WorkflowContext(signal=signal, publisher_dispatch=publisher_dispatch),
        decision,
    )
