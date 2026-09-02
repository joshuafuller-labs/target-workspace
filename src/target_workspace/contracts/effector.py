"""Effector plugin protocol (tw-12l).

Per ADR 0019. Effectors are queried (not pushed) — they answer
'given this target + my inventory, what are the dispatch options?'
with a ranked list. The operator still moves the card through the
approval column; Effectors never auto-engage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from target_workspace.models.target import Target


@dataclass(frozen=True)
class ResourceCapability:
    """One asset available for dispatch.

    Generic across domains — works for SAR squads, fires batteries,
    medevac helos, drone teams. Domain-specific fields live in
    ``custom_fields`` so each Effector reads what it needs.
    """

    resource_id: str
    kind: str  # 'battery' | 'drone' | 'swift-water' | 'medevac' | ...
    lat: float | None = None
    lon: float | None = None
    status: str = "available"  # 'available' | 'committed' | 'refit'
    capabilities: list[str] = field(default_factory=list)
    custom_fields: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MatchConstraints:
    """Operator-applied filters at the moment of query."""

    rules_of_engagement: str | None = None
    max_eta_seconds: int | None = None
    exclude_resource_ids: list[str] = field(default_factory=list)
    weather: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EffectorMatch:
    """One option in the ranked dispatch list."""

    resource_id: str
    score: float  # 0..1; higher is better
    rationale: str
    eta_seconds: int | None = None
    risk_factors: list[str] = field(default_factory=list)
    dispatch_via: str | None = None  # publisher name to fan out the chosen option


@runtime_checkable
class Effector(Protocol):
    """Plugin protocol — implementations register via the
    ``target_workspace.effectors`` entry-point group."""

    name: str

    def match(
        self,
        *,
        target: Target,
        inventory: list[ResourceCapability],
        constraints: MatchConstraints,
    ) -> list[EffectorMatch]:
        """Return a ranked list of effector options. Empty list means
        'no eligible effector for this target.' Higher score first."""
        ...
