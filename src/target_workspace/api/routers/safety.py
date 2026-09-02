"""/v1/safety — wellness/safety derived endpoints (tw-zba3)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from target_workspace.api.dependencies import require_token_scope
from target_workspace.api.presence import snapshot
from target_workspace.api.safety import is_stationary
from target_workspace.db.tables import UserTable

router = APIRouter(prefix="/v1/safety", tags=["safety"])


@router.get("/stationary")
def stationary_callsigns(
    min_minutes: float = Query(default=5.0, ge=0.0),
    max_drift_m: float = Query(default=25.0, ge=0.0),
    user: UserTable = Depends(require_token_scope("safety:read")),
) -> list[dict[str, Any]]:
    """Return callsigns currently flagged as stationary-too-long.

    Per tw-zba3. Each entry: { callsign, lat, lon, time }.
    """
    return [
        {
            "callsign": entry.callsign,
            "lat": entry.lat,
            "lon": entry.lon,
            "time": entry.time_iso,
        }
        for entry in snapshot()
        if is_stationary(
            callsign=entry.callsign,
            min_minutes=min_minutes,
            max_drift_m=max_drift_m,
        )
    ]
