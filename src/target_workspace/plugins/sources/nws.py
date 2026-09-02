"""NWS / NOAA weather alerts Source adapter (tw-sfu0).

Maps a NWS GeoJSON Feature (from api.weather.gov/alerts/active) to a
Target-shaped dict. Polygon → polygon_vertices; severity/area/timing
preserved in custom_fields so the SPA can render an alerts panel.
"""

from __future__ import annotations

from typing import Any

from target_workspace.plugins.loader import register_source


class NwsSource:
    name = "nws"

    def normalize(
        self,
        payload: dict[str, Any],
        normalization_map: dict[str, Any],
    ) -> dict[str, Any]:
        _ = normalization_map  # NWS shape is fixed; map is unused
        props = payload.get("properties") or {}
        geom = payload.get("geometry")

        vertices, kind, lat, lon = _extract_geometry(geom)

        return {
            "name": props.get("headline") or props.get("event") or "NWS Alert",
            "lat": lat,
            "lon": lon,
            "geometry_kind": kind,
            "polygon_vertices": vertices,
            "custom_fields": {
                "event": props.get("event"),
                "severity": props.get("severity"),
                "certainty": props.get("certainty"),
                "urgency": props.get("urgency"),
                "area": props.get("areaDesc"),
                "effective": props.get("effective"),
                "ends": props.get("ends"),
                "sender": props.get("senderName"),
            },
        }


def _extract_geometry(
    geom: dict[str, Any] | None,
) -> tuple[list[list[float]] | None, str, float, float]:
    if not geom or "type" not in geom:
        return None, "point", 0.0, 0.0
    t = geom["type"]
    if t == "Polygon":
        ring = geom["coordinates"][0]
        vertices = [[float(c[0]), float(c[1])] for c in ring]
    elif t == "MultiPolygon":
        ring = geom["coordinates"][0][0]
        vertices = [[float(c[0]), float(c[1])] for c in ring]
    else:
        return None, "point", 0.0, 0.0
    lon, lat = _centroid(vertices)
    return vertices, "polygon", lat, lon


def _centroid(vertices: list[list[float]]) -> tuple[float, float]:
    """Naive arithmetic centroid — good enough to drop a map pin on the
    alert polygon. Real shoelace centroid is overkill for a county
    bounding outline."""
    if not vertices:
        return 0.0, 0.0
    xs = [v[0] for v in vertices]
    ys = [v[1] for v in vertices]
    return sum(xs) / len(xs), sum(ys) / len(ys)


register_source(NwsSource.name, NwsSource)
