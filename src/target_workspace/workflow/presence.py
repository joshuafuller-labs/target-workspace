"""Presence signal ingestion into the workflow pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlmodel import Session, select

from target_workspace.db.tables import TargetTable
from target_workspace.workflow.engine import (
    PresenceObserved,
    PromotionDenied,
    WorkflowContext,
    apply_decision,
    evaluate,
)
from target_workspace.workflow.geofence import evaluate_geofence


@dataclass(frozen=True)
class PresenceWorkflowOutcome:
    target_id: UUID
    event: str
    verdict: str
    reason: str
    proposed_by: str
    nomination_id: UUID | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "target_id": str(self.target_id),
            "event": self.event,
            "verdict": self.verdict,
            "reason": self.reason,
            "proposed_by": self.proposed_by,
            "nomination_id": str(self.nomination_id) if self.nomination_id is not None else None,
        }


@dataclass(frozen=True)
class PresenceWorkflowResult:
    transitions: list[dict[str, Any]]
    outcomes: list[PresenceWorkflowOutcome]


def evaluate_presence_workflows(
    session: Session,
    *,
    workspace_id: UUID,
    actor_id: UUID,
    callsign: str,
    lat: float,
    lon: float,
    ce: float | None,
    source: str | None,
) -> PresenceWorkflowResult:
    rows = session.exec(
        select(TargetTable).where(TargetTable.workspace_id == workspace_id),
    ).all()
    transitions: list[dict[str, Any]] = []
    outcomes: list[PresenceWorkflowOutcome] = []
    for target in rows:
        assigned_callsigns = list(target.assigned_callsigns or [])
        if callsign not in assigned_callsigns:
            continue
        target_transitions = evaluate_geofence(
            target_id=target.id,
            target_lat=target.lat,
            target_lon=target.lon,
            target_ce=target.ce,
            callsign=callsign,
            pli_lat=lat,
            pli_lon=lon,
        )
        transitions.extend(target_transitions)
        for transition in target_transitions:
            geo_attestation = {
                "lat": lat,
                "lon": lon,
                "source": source,
                "ce": ce,
                "distance_m": transition["distance_m"],
                "radius_m": transition["radius_m"],
            }
            signal = PresenceObserved(
                target_id=target.id,
                actor_id=actor_id,
                event=transition["event"],
                callsign=callsign,
                assigned_callsigns=assigned_callsigns,
                callsigns_already_arrived={callsign},
                geo_attestation=geo_attestation,
                justification=f"{callsign} {transition['event']}",
            )
            decision = evaluate(session, signal)
            result_nomination_id = None
            if decision.verdict in {"allow", "propose"}:
                try:
                    result = apply_decision(session, WorkflowContext(signal=signal), decision)
                except PromotionDenied as exc:
                    outcomes.append(
                        PresenceWorkflowOutcome(
                            target_id=target.id,
                            event=transition["event"],
                            verdict="deny",
                            reason=str(exc),
                            proposed_by="workflow:apply",
                        )
                    )
                    continue
                result_nomination_id = result.nomination_id
            outcomes.append(
                PresenceWorkflowOutcome(
                    target_id=target.id,
                    event=transition["event"],
                    verdict=decision.verdict,
                    reason=decision.reason,
                    proposed_by=decision.proposed_by,
                    nomination_id=result_nomination_id,
                )
            )
    return PresenceWorkflowResult(transitions=transitions, outcomes=outcomes)
