"""ACLED conflict-event Source adapter (tw-kb2j).

Maps one ACLED event (column dict from the data-export API) to a
Target. Curated event-type taxonomy is preserved in custom_fields.

ACLED field reference: https://acleddata.com/resources/general-guides/
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


def _safe_int(v: Any) -> int:
    try:
        s = str(v).strip()
        if not s:
            return 0
        return int(s)
    except (TypeError, ValueError):
        return 0


class AcledSource:
    name = "acled"

    def normalize(
        self,
        payload: dict[str, Any],
        normalization_map: dict[str, Any],
    ) -> dict[str, Any]:
        _ = normalization_map
        actor1 = (payload.get("actor1") or "").strip()
        actor2 = (payload.get("actor2") or "").strip()
        location = (payload.get("location") or "").strip()
        event_type = (payload.get("event_type") or "").strip()

        parts: list[str] = []
        if event_type:
            parts.append(event_type)
        if location:
            parts.append(location)
        name = " — ".join(parts) if parts else f"ACLED {payload.get('data_id', '')}".strip()

        return {
            "name": name,
            "lat": _safe_float(payload.get("latitude")),
            "lon": _safe_float(payload.get("longitude")),
            "cot_type": "a-h-G-I",
            "remarks": payload.get("notes"),
            "custom_fields": {
                "event_type": event_type or None,
                "sub_event_type": payload.get("sub_event_type") or None,
                "actor1": actor1 or None,
                "actor2": actor2 or None,
                "interaction": payload.get("interaction"),
                "country": payload.get("country"),
                "admin1": payload.get("admin1"),
                "location": location or None,
                "fatalities": _safe_int(payload.get("fatalities")),
                "event_date": payload.get("event_date"),
                "source_publication": payload.get("source"),
                "source_scale": payload.get("source_scale"),
                "data_id": payload.get("data_id"),
            },
        }


register_source(AcledSource.name, AcledSource)
