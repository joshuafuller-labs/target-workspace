"""Geofence arrival/departure state machine."""

from __future__ import annotations

import math
from threading import Lock
from typing import Any

_state: dict[tuple[str, str], bool] = {}
_lock = Lock()

MIN_RADIUS_M = 100.0


def default_radius_m(ce: float | None) -> float:
    if ce is None or ce <= 0.0:
        return MIN_RADIUS_M
    return max(MIN_RADIUS_M, float(ce))


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def evaluate_geofence(
    *,
    target_id: Any,
    target_lat: float,
    target_lon: float,
    target_ce: float | None,
    callsign: str,
    pli_lat: float,
    pli_lon: float,
    radius_m: float | None = None,
) -> list[dict[str, Any]]:
    radius = radius_m if radius_m is not None else default_radius_m(target_ce)
    distance = _haversine_m(target_lat, target_lon, pli_lat, pli_lon)
    inside_now = distance <= radius

    key = (str(target_id), callsign)
    with _lock:
        was_inside = _state.get(key)
        _state[key] = inside_now

    if was_inside is None:
        if inside_now:
            return [
                {
                    "event": "presence.arrived",
                    "target_id": str(target_id),
                    "callsign": callsign,
                    "distance_m": distance,
                    "radius_m": radius,
                },
            ]
        return []
    if was_inside and not inside_now:
        return [
            {
                "event": "presence.departed",
                "target_id": str(target_id),
                "callsign": callsign,
                "distance_m": distance,
                "radius_m": radius,
            },
        ]
    if not was_inside and inside_now:
        return [
            {
                "event": "presence.arrived",
                "target_id": str(target_id),
                "callsign": callsign,
                "distance_m": distance,
                "radius_m": radius,
            },
        ]
    return []


def reset_geofence_state() -> None:
    with _lock:
        _state.clear()
