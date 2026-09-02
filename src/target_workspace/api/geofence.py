"""Compatibility exports for the workflow geofence state machine."""

from target_workspace.workflow.geofence import (
    MIN_RADIUS_M,
    default_radius_m,
    evaluate_geofence,
    reset_geofence_state,
)

__all__ = [
    "MIN_RADIUS_M",
    "default_radius_m",
    "evaluate_geofence",
    "reset_geofence_state",
]
