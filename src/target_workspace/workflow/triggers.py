"""Presence workflow trigger policy.

Per-board rules fire on geofence transitions and propose a column move.
Routers persist the rules; this module evaluates them as workflow Decisions.

Condition grammar:
  - 'min_assignees:N' fires if the target has at least N assigned callsigns
  - 'all_assigned' fires only when every assigned callsign has arrived
  - 'any' fires on the event alone
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from target_workspace.contracts.promotion_policy import Decision


@dataclass(frozen=True)
class WorkflowTriggerRule:
    id: str
    board_id: str
    trigger: str
    condition: str
    action_move_to_column_id: str
    justification_template: str


@dataclass(frozen=True)
class PresenceWorkflowPolicy:
    """ADR 0021 policy adapter for persisted presence workflow triggers."""

    rule: WorkflowTriggerRule
    event: str
    target_board_id: str
    target_column_id: str
    target_id: UUID
    callsign: str
    assigned_callsigns: list[str]
    callsigns_already_arrived: set[str] | None = None
    geo_attestation: dict[str, Any] | None = None
    approver_role: str = "approver"

    @property
    def name(self) -> str:
        return f"workflow:presence:{self.rule.id}"

    def evaluate(self) -> Decision:
        if self.rule.board_id != self.target_board_id:
            return Decision.abstain(reason="rule board mismatch", proposed_by=self.name)
        if self.rule.trigger != self.event:
            return Decision.abstain(reason="event mismatch", proposed_by=self.name)
        if self.rule.action_move_to_column_id == self.target_column_id:
            return Decision.abstain(reason="target already in destination", proposed_by=self.name)
        if not _condition_met(
            self.rule.condition,
            assigned_callsigns=self.assigned_callsigns,
            callsigns_already_arrived=self.callsigns_already_arrived,
        ):
            return Decision.abstain(reason="condition not met", proposed_by=self.name)

        reason = self.rule.justification_template.format(
            callsign=self.callsign,
            trigger=self.event,
        )
        return Decision.propose(
            reason=reason,
            proposed_by=self.name,
            approver_role=self.approver_role,
            target_id=self.target_id,
            to_column_id=_uuid_or_none(self.rule.action_move_to_column_id),
            evidence={
                "rule_id": self.rule.id,
                "event": self.event,
                "callsign": self.callsign,
                "geo_attestation": self.geo_attestation,
            },
        )


def _condition_met(
    condition: str,
    *,
    assigned_callsigns: list[str],
    callsigns_already_arrived: set[str] | None,
) -> bool:
    if condition == "any":
        return True
    if condition.startswith("min_assignees:"):
        try:
            n = int(condition.split(":", 1)[1])
        except ValueError:
            return False
        return len(assigned_callsigns) >= n
    if condition == "all_assigned":
        if not assigned_callsigns:
            return False
        arrived = callsigns_already_arrived or set()
        return all(c in arrived for c in assigned_callsigns)
    return False


def _uuid_or_none(value: str) -> UUID | None:
    try:
        return UUID(value)
    except ValueError:
        return None


def _attestation(
    *,
    pli_lat: float | None,
    pli_lon: float | None,
    pli_source: str | None,
    pli_ce: float | None,
    distance_m: float | None,
    radius_m: float | None,
) -> dict[str, Any] | None:
    if pli_lat is None or pli_lon is None:
        return None
    return {
        "lat": pli_lat,
        "lon": pli_lon,
        "pli_source": pli_source,
        "ce": pli_ce,
        "distance_m": distance_m,
        "radius_m": radius_m,
    }


def presence_decisions(
    *,
    rules: Iterable[WorkflowTriggerRule],
    event: str,
    target_board_id: str,
    target_column_id: str,
    target_id: UUID,
    callsign: str,
    assigned_callsigns: list[str],
    callsigns_already_arrived: set[str] | None = None,
    geo_attestation: dict[str, Any] | None = None,
) -> list[Decision]:
    return [
        PresenceWorkflowPolicy(
            rule=rule,
            event=event,
            target_board_id=target_board_id,
            target_column_id=target_column_id,
            target_id=target_id,
            callsign=callsign,
            assigned_callsigns=assigned_callsigns,
            callsigns_already_arrived=callsigns_already_arrived,
            geo_attestation=geo_attestation,
        ).evaluate()
        for rule in rules
    ]


def consider_actions(
    *,
    rules: Iterable[WorkflowTriggerRule],
    event: str,
    target_board_id: str,
    target_column_id: str,
    callsign: str,
    assigned_callsigns: list[str],
    callsigns_already_arrived: set[str] | None = None,
    pli_lat: float | None = None,
    pli_lon: float | None = None,
    pli_source: str | None = None,
    pli_ce: float | None = None,
    distance_m: float | None = None,
    radius_m: float | None = None,
) -> list[dict[str, Any]]:
    """Compatibility wrapper returning legacy action dicts from Decisions."""
    rules_list = list(rules)
    geo_attestation = _attestation(
        pli_lat=pli_lat,
        pli_lon=pli_lon,
        pli_source=pli_source,
        pli_ce=pli_ce,
        distance_m=distance_m,
        radius_m=radius_m,
    )
    decisions = presence_decisions(
        rules=rules_list,
        event=event,
        target_board_id=target_board_id,
        target_column_id=target_column_id,
        target_id=UUID(int=0),
        callsign=callsign,
        assigned_callsigns=assigned_callsigns,
        callsigns_already_arrived=callsigns_already_arrived,
        geo_attestation=geo_attestation,
    )
    return [
        {
            "rule_id": decision.evidence["rule_id"],
            "move_to_column_id": rule.action_move_to_column_id,
            "justification": decision.reason,
            "geo_attestation": decision.evidence["geo_attestation"],
        }
        for rule, decision in zip(rules_list, decisions, strict=True)
        if decision.verdict == "propose"
    ]
