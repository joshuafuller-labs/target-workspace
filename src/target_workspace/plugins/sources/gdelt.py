"""GDELT 2.0 Source adapter (tw-s8kd).

Maps one parsed GDELT 2.0 events-table row (column dict, post-CSV
parse) to a Target dict. CSV fetch / unzip happens upstream in the
ingest pipeline.

GDELT field reference: http://data.gdeltproject.org/documentation/GDELT-Event_Codebook-V2.0.pdf
"""

from __future__ import annotations

from typing import Any

from target_workspace.plugins.loader import register_source


def _safe_float(v: Any) -> float:
    try:
        s = str(v).strip()
        if not s:
            return 0.0
        return float(s)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(v: Any) -> int | None:
    try:
        s = str(v).strip()
        if not s:
            return None
        return int(s)
    except (TypeError, ValueError):
        return None


class GdeltSource:
    name = "gdelt"

    def normalize(
        self,
        payload: dict[str, Any],
        normalization_map: dict[str, Any],
    ) -> dict[str, Any]:
        _ = normalization_map
        actor1 = (payload.get("Actor1Name") or "").strip()
        actor2 = (payload.get("Actor2Name") or "").strip()
        place = (payload.get("ActionGeo_Fullname") or "").strip()
        cameo = (payload.get("EventCode") or "").strip()

        parts = [p for p in (actor1, actor2) if p]
        if parts:
            name = " / ".join(parts)
            if place:
                name = f"{name} — {place}"
        elif place:
            name = place
        else:
            name = f"GDELT event {payload.get('GlobalEventID', '')}".strip()

        return {
            "name": name,
            "lat": _safe_float(payload.get("ActionGeo_Lat")),
            "lon": _safe_float(payload.get("ActionGeo_Long")),
            "cot_type": "a-u-G-I",
            "source": payload.get("SOURCEURL"),
            "custom_fields": {
                "cameo_code": cameo,
                "actor1": actor1 or None,
                "actor2": actor2 or None,
                "quad_class": _safe_int(payload.get("QuadClass")),
                "goldstein_scale": _safe_float(payload.get("GoldsteinScale")),
                "place": place or None,
                "sql_date": payload.get("SQLDATE"),
                "global_event_id": payload.get("GlobalEventID"),
            },
        }


register_source(GdeltSource.name, GdeltSource)
