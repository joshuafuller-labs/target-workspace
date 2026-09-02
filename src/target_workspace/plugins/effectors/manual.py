"""Manual Effector — reference plugin (tw-12l).

The simplest possible Effector. Scores inventory resources by:

  - status (available > committed > refit)
  - inverse distance to target (closer = higher score)
  - capability match against the target's cot_type (rough heuristic)

Real domain Effectors (Kropyva-style fires, NATO MIP, TAK fires-net)
each replace this with rich logic; this exists so plugin authors have
a working shape to copy.
"""

from __future__ import annotations

import math

from target_workspace.contracts.effector import (
    EffectorMatch,
    MatchConstraints,
    ResourceCapability,
)
from target_workspace.models.target import Target
from target_workspace.plugins.loader import register_effector

_STATUS_WEIGHT = {"available": 1.0, "committed": 0.4, "refit": 0.1}


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class ManualEffector:
    name = "manual_effector"

    def match(
        self,
        *,
        target: Target,
        inventory: list[ResourceCapability],
        constraints: MatchConstraints,
    ) -> list[EffectorMatch]:
        excluded = set(constraints.exclude_resource_ids)
        matches: list[EffectorMatch] = []
        for r in inventory:
            if r.resource_id in excluded:
                continue
            status_score = _STATUS_WEIGHT.get(r.status, 0.0)
            if status_score == 0.0:
                continue
            distance_score = 1.0
            eta_seconds: int | None = None
            if r.lat is not None and r.lon is not None:
                d = _haversine_m(target.lat, target.lon, r.lat, r.lon)
                # Linear fall-off; resources within 1km score ~1.0, 50km scores ~0.05.
                distance_score = max(0.05, 1.0 - d / 50_000.0)
                # Naive ETA assuming 60 km/h overland; tunable per kind in real impls.
                eta_seconds = int(d / (60_000.0 / 3600.0))
            score = round(status_score * distance_score, 3)
            rationale_parts: list[str] = [r.kind, f"status={r.status}"]
            if r.capabilities:
                rationale_parts.append("capabilities=" + ",".join(r.capabilities))
            matches.append(
                EffectorMatch(
                    resource_id=r.resource_id,
                    score=score,
                    rationale=" · ".join(rationale_parts),
                    eta_seconds=eta_seconds,
                ),
            )
        matches.sort(key=lambda m: m.score, reverse=True)
        # Honor max_eta_seconds filter (post-sort so a tight cutoff still
        # returns the best of the qualifying set).
        if constraints.max_eta_seconds is not None:
            matches = [
                m
                for m in matches
                if m.eta_seconds is None or m.eta_seconds <= constraints.max_eta_seconds
            ]
        return matches


register_effector(ManualEffector.name, ManualEffector)
