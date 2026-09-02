"""Tests for the pure workflow geofence state machine."""

from __future__ import annotations

from target_workspace.workflow.geofence import (
    default_radius_m,
    evaluate_geofence,
    reset_geofence_state,
)


def test_workflow_geofence_emits_arrival_once_for_inside_pli() -> None:
    reset_geofence_state()

    first = evaluate_geofence(
        target_id="target-1",
        target_lat=35.60000,
        target_lon=-82.55000,
        target_ce=None,
        callsign="MEDIC-1",
        pli_lat=35.60001,
        pli_lon=-82.55000,
    )
    second = evaluate_geofence(
        target_id="target-1",
        target_lat=35.60000,
        target_lon=-82.55000,
        target_ce=None,
        callsign="MEDIC-1",
        pli_lat=35.60001,
        pli_lon=-82.55000,
    )

    assert first[0]["event"] == "presence.arrived"
    assert second == []


def test_workflow_geofence_default_radius_floor() -> None:
    assert default_radius_m(None) == 100.0
    assert default_radius_m(10.0) == 100.0
    assert default_radius_m(250.0) == 250.0
