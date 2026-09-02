"""PromotionPolicy plugin contract - decides when a target moves between columns.

Custom policies (for example, "require two-person integrity at FINISH" or
"auto-publish if source is XYZ and confidence > N") implement this Protocol.

Implementations are discovered via the `target_workspace.policies` entry-points
group.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal, Protocol, runtime_checkable
from uuid import UUID

DecisionVerdict = Literal["allow", "deny", "propose", "abstain"]


@dataclass(frozen=True)
class Signal:
    """ADR 0021 signal envelope consumed by promotion policies."""

    kind: str
    emitted_by: str
    occurred_at: datetime
    target_id: UUID | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind.startswith("external:") and len(self.kind) <= len("external:"):
            msg = "external signal kinds must include a namespace"
            raise ValueError(msg)


@dataclass(frozen=True)
class DecisionContext:
    """Read-only context exposed to pure policy evaluation."""

    board_id: UUID | None
    target: Any | None = None
    board: Any | None = None
    actor: Any | None = None
    services: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Decision:
    """Pure policy verdict data; applying side effects happens elsewhere."""

    verdict: DecisionVerdict
    reason: str
    proposed_by: str
    evidence: dict[str, Any] = field(default_factory=dict)
    target_id: UUID | None = None
    to_column_id: UUID | None = None
    approver_role: str | None = None

    def __post_init__(self) -> None:
        if self.verdict == "propose" and not self.approver_role:
            msg = "propose decisions require approver_role"
            raise ValueError(msg)
        if self.verdict != "propose" and self.approver_role is not None:
            msg = "approver_role is only valid for propose decisions"
            raise ValueError(msg)

    @classmethod
    def allow(
        cls,
        *,
        reason: str,
        proposed_by: str,
        evidence: dict[str, Any] | None = None,
        target_id: UUID | None = None,
        to_column_id: UUID | None = None,
    ) -> Decision:
        return cls(
            verdict="allow",
            reason=reason,
            proposed_by=proposed_by,
            evidence=evidence or {},
            target_id=target_id,
            to_column_id=to_column_id,
        )

    @classmethod
    def deny(
        cls,
        *,
        reason: str,
        proposed_by: str,
        evidence: dict[str, Any] | None = None,
        target_id: UUID | None = None,
        to_column_id: UUID | None = None,
    ) -> Decision:
        return cls(
            verdict="deny",
            reason=reason,
            proposed_by=proposed_by,
            evidence=evidence or {},
            target_id=target_id,
            to_column_id=to_column_id,
        )

    @classmethod
    def propose(
        cls,
        *,
        reason: str,
        proposed_by: str,
        approver_role: str | None = None,
        evidence: dict[str, Any] | None = None,
        target_id: UUID | None = None,
        to_column_id: UUID | None = None,
    ) -> Decision:
        return cls(
            verdict="propose",
            reason=reason,
            proposed_by=proposed_by,
            approver_role=approver_role,
            evidence=evidence or {},
            target_id=target_id,
            to_column_id=to_column_id,
        )

    @classmethod
    def abstain(
        cls,
        *,
        reason: str,
        proposed_by: str,
        evidence: dict[str, Any] | None = None,
        target_id: UUID | None = None,
        to_column_id: UUID | None = None,
    ) -> Decision:
        return cls(
            verdict="abstain",
            reason=reason,
            proposed_by=proposed_by,
            evidence=evidence or {},
            target_id=target_id,
            to_column_id=to_column_id,
        )


@runtime_checkable
class PromotionPolicy(Protocol):
    """Decides whether a target may advance from one column to another."""

    name: str
    """Stable identifier for this policy type."""

    def evaluate(self, signal: Signal, ctx: DecisionContext) -> Decision:
        """Return a pure decision for the given signal and read-only context."""
        ...
