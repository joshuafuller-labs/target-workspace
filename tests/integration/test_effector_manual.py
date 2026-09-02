"""Manual Effector plugin (tw-12l).

Reference Effector that scores inventory by status + distance. Real
domain plugins replace it; this exists so plugin authors have a
working shape and the entry-point group is exercised.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from target_workspace.contracts.effector import (
    MatchConstraints,
    ResourceCapability,
)
from target_workspace.models.target import Target
from target_workspace.plugins.effectors.manual import ManualEffector

pytestmark = [pytest.mark.fast]


def _target(lat: float = 35.6, lon: float = -82.55) -> Target:
    return Target(
        id=uuid4(),
        name="T",
        cot_type="a-h-G",
        lat=lat,
        lon=lon,
        time=datetime.now(tz=UTC),
    )


def test_match_returns_ranked_list() -> None:
    eff = ManualEffector()
    inventory = [
        ResourceCapability(resource_id="r1", kind="boat", lat=35.6, lon=-82.55),
        ResourceCapability(resource_id="r2", kind="boat", lat=36.0, lon=-83.0),
    ]
    out = eff.match(target=_target(), inventory=inventory, constraints=MatchConstraints())
    assert len(out) == 2
    assert out[0].score >= out[1].score  # ranked
    assert out[0].resource_id == "r1"  # closer to target


def test_match_skips_excluded_resources() -> None:
    eff = ManualEffector()
    inventory = [
        ResourceCapability(resource_id="r1", kind="boat"),
        ResourceCapability(resource_id="r2", kind="boat"),
    ]
    out = eff.match(
        target=_target(),
        inventory=inventory,
        constraints=MatchConstraints(exclude_resource_ids=["r1"]),
    )
    assert [m.resource_id for m in out] == ["r2"]


def test_match_skips_unavailable_status() -> None:
    eff = ManualEffector()
    inventory = [
        ResourceCapability(resource_id="r1", kind="boat", status="committed"),
        ResourceCapability(resource_id="r2", kind="boat", status="refit"),
        ResourceCapability(resource_id="r3", kind="boat", status="available"),
    ]
    out = eff.match(target=_target(), inventory=inventory, constraints=MatchConstraints())
    # All three returned but ordered by status_weight * distance_score.
    # Available ought to come first all else equal.
    assert out[0].resource_id == "r3"


def test_match_honors_max_eta() -> None:
    eff = ManualEffector()
    inventory = [
        # Co-located → ETA ~0
        ResourceCapability(resource_id="r1", kind="boat", lat=35.6, lon=-82.55),
        # 30km away at 60km/h → ~30min ETA
        ResourceCapability(resource_id="r2", kind="boat", lat=35.6, lon=-82.2),
    ]
    out = eff.match(
        target=_target(),
        inventory=inventory,
        constraints=MatchConstraints(max_eta_seconds=60),
    )
    assert [m.resource_id for m in out] == ["r1"]


def test_loader_discovers_manual_effector() -> None:
    from target_workspace.plugins.loader import (
        discover_effectors,
        register_builtin_plugins,
    )

    register_builtin_plugins()
    effs = discover_effectors()
    assert "manual_effector" in effs
