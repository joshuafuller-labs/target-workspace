"""Geo-attested workflow trigger actions (tw-f4yo).

When the workflow trigger engine emits an action in response to a
geofence event, it carries the geo-attestation:
  - lat/lon: the assignee's PLI fix at the moment of trigger
  - pli_source: which Source fed the PLI (TAK server, CoT-in, etc)
  - distance_m + radius_m: how the geofence matched
  - ce: circular error if the PLI carried it

The action dict shape gains a top-level 'geo_attestation' key the
caller writes verbatim into audit metadata.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.fast]


def test_consider_actions_carries_geo_attestation() -> None:
    from target_workspace.api.workflow_triggers import (
        WorkflowTriggerRule,
        consider_actions,
    )

    rule = WorkflowTriggerRule(
        id="r1",
        board_id="b1",
        trigger="presence.arrived",
        condition="min_assignees:1",
        action_move_to_column_id="col-2",
        justification_template="{callsign} arrived",
    )
    actions = consider_actions(
        rules=[rule],
        event="presence.arrived",
        target_board_id="b1",
        target_column_id="col-1",
        callsign="DEPUTY-44",
        assigned_callsigns=["DEPUTY-44"],
        pli_lat=29.7541,
        pli_lon=-95.4012,
        pli_source="atak-server-eoc",
        pli_ce=12.0,
        distance_m=47.3,
        radius_m=100.0,
    )
    assert len(actions) == 1
    a = actions[0]
    assert "geo_attestation" in a
    geo = a["geo_attestation"]
    assert geo["lat"] == 29.7541
    assert geo["lon"] == -95.4012
    assert geo["pli_source"] == "atak-server-eoc"
    assert geo["ce"] == 12.0
    assert geo["distance_m"] == 47.3
    assert geo["radius_m"] == 100.0


def test_consider_actions_geo_attestation_optional() -> None:
    """Older callers that don't supply PLI provenance still work; the
    geo_attestation dict carries only what was provided."""
    from target_workspace.api.workflow_triggers import (
        WorkflowTriggerRule,
        consider_actions,
    )

    rule = WorkflowTriggerRule(
        id="r1",
        board_id="b1",
        trigger="presence.arrived",
        condition="any",
        action_move_to_column_id="col-2",
        justification_template="x",
    )
    actions = consider_actions(
        rules=[rule],
        event="presence.arrived",
        target_board_id="b1",
        target_column_id="col-1",
        callsign="X",
        assigned_callsigns=["X"],
    )
    assert len(actions) == 1
    a = actions[0]
    # Backwards-compatible: geo_attestation is None when caller didn't supply.
    assert a.get("geo_attestation") is None
