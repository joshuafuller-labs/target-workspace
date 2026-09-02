"""USGS earthquake feed Source adapter (tw-8zfi).

Maps a USGS GeoJSON Feature (from
earthquake.usgs.gov/earthquakes/feed/v1.0/summary/*) to a Target dict.
Trivial demo Source for the 'wire any geo feed in 30 lines' pitch.
"""

from __future__ import annotations

from typing import Any

from target_workspace.plugins.loader import register_source


class UsgsSource:
    name = "usgs"

    def normalize(
        self,
        payload: dict[str, Any],
        normalization_map: dict[str, Any],
    ) -> dict[str, Any]:
        _ = normalization_map
        props = payload.get("properties") or {}
        geom = payload.get("geometry") or {}
        coords = geom.get("coordinates") or [0.0, 0.0]
        lon = float(coords[0])
        lat = float(coords[1])
        depth_km = float(coords[2]) if len(coords) > 2 else None  # noqa: PLR2004 — GeoJSON coords are [lon, lat, depth]; index 2 is depth
        return {
            "name": props.get("title") or props.get("place") or "Seismic event",
            "lat": lat,
            "lon": lon,
            "geometry_kind": "point",
            "source": props.get("url"),
            "custom_fields": {
                "magnitude": props.get("mag"),
                "depth_km": depth_km,
                "place": props.get("place"),
                "tsunami": props.get("tsunami"),
                "felt": props.get("felt"),
                "time_ms": props.get("time"),
                "updated_ms": props.get("updated"),
            },
        }


register_source(UsgsSource.name, UsgsSource)
