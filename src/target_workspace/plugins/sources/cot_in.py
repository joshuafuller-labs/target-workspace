"""CoT-in Source — listens for inbound CoT XML from a TAK Server.

Closes the last MVP P0 (paired with tw-h7x http_webhook): anyone with
an existing CoT producer (TAK Server, TAKX, FreeTAKServer — well, NOT
FTS per project policy — but any standard ATAK client) can publish
to us with zero new tooling.

This module owns the parser side. The async listener that calls it on
each frame off the wire lives in cot_in_listener.py.

CoT 2.0 schema we map:
    <event uid="..." type="..." start="...">
      <point lat lon hae ce le/>
      <detail>
        <contact callsign="..."/>
        <remarks>...</remarks>
        <__source system="..."/>      (our publisher's attribution ext)
        <ellipse major minor angle/>  (our publisher's geometry ext)
      </detail>
    </event>

Inverse of plugins/publishers/raw_cot.py:target_to_cot_xml — same
schema, opposite direction. Round-trips losslessly for our own events.

tw-o13.
"""

from __future__ import annotations

import contextlib
import logging

# ET kept only for ParseError/Element types; untrusted parsing uses defusedxml
# (DET) below — suppress semgrep's use-defused-xml on this import.
import xml.etree.ElementTree as ET  # nosemgrep
from datetime import datetime
from typing import Any

import defusedxml.ElementTree as DET
from defusedxml import DefusedXmlException

from target_workspace.plugins.loader import register_source
from target_workspace.utc_datetime import _iso_utc  # noqa: F401 — used elsewhere

log = logging.getLogger(__name__)


class CotInSource:
    name = "cot_in"

    def normalize(
        self,
        payload: dict[str, Any],
        normalization_map: dict[str, Any],
    ) -> dict[str, Any]:
        """For CoT-in, the listener pre-parses XML to a Target-shaped
        dict; this normalize call is the no-op identity passthrough.
        Kept to satisfy the Source contract for plugin discovery."""
        _ = normalization_map
        return payload


def parse_cot_xml(xml_bytes: bytes) -> dict[str, Any] | None:  # noqa: PLR0911, PLR0912 — flat CoT-field extraction reads clearer as one pass than split helpers
    """Parse a CoT 2.0 XML event into a Target-compatible dict.

    Returns None on:
      - malformed XML
      - missing required attributes (type, point)
      - any parse error we'd rather drop than crash the connection on

    Returns a dict with at minimum {name, cot_type, lat, lon, time}.
    Optional fields populated when present in the XML: ce, le,
    geometry_kind, ellipse, remarks, source. The dict also carries a
    `_cot_kind` hint ('event' | 'pli') so the listener can decide to
    drop PLI broadcasts by default (handled by the listener, not here).
    """
    try:
        # defusedxml hardens against XXE/billion-laughs — CoT XML is untrusted
        # network input. ET.ParseError covers malformed XML; DefusedXmlException
        # covers entity/DTD attacks. Either way, drop the packet.
        root = DET.fromstring(xml_bytes)
    except (ET.ParseError, DefusedXmlException):
        return None

    if root.tag != "event":
        return None

    cot_type = root.attrib.get("type")
    if not cot_type:
        return None

    point = root.find("point")
    if point is None:
        return None

    try:
        lat = float(point.attrib["lat"])
        lon = float(point.attrib["lon"])
    except (KeyError, ValueError):
        return None

    # `start` is when the source OBSERVED the event (preferred). Fall
    # back to `time` (when the producer assembled the message) if
    # start is missing.
    raw_time = root.attrib.get("start") or root.attrib.get("time")
    try:
        observed = _parse_cot_dtg(raw_time) if raw_time else None
    except ValueError:
        observed = None
    if observed is None:
        return None

    out: dict[str, Any] = {
        "cot_type": cot_type,
        "lat": lat,
        "lon": lon,
        "time": observed,
    }

    # Optional point precision.
    for key in ("hae", "ce", "le"):
        if key in point.attrib:
            with contextlib.suppress(ValueError):
                out[key] = float(point.attrib[key])

    detail = root.find("detail")
    contact = detail.find("contact") if detail is not None else None
    callsign = contact.attrib.get("callsign") if contact is not None else None
    out["name"] = callsign or root.attrib.get("uid", "unknown")

    # Remarks → free-form analyst notes carried back.
    if detail is not None:
        remarks_el = detail.find("remarks")
        if remarks_el is not None and remarks_el.text:
            out["remarks"] = remarks_el.text.strip()

        # Our publisher's <__source system="..."/> attribution extension.
        src_el = detail.find("__source")
        if src_el is not None and "system" in src_el.attrib:
            out["source"] = src_el.attrib["system"]

        # Our publisher's <ellipse major minor angle/> geometry ext.
        ell_el = detail.find("ellipse")
        if ell_el is not None:
            try:
                # CoT uses full-axis diameters; we store semi-axes.
                out["geometry_kind"] = "ellipse"
                out["ellipse"] = {
                    "semi_major_m": float(ell_el.attrib.get("major", 0)) / 2.0,
                    "semi_minor_m": float(ell_el.attrib.get("minor", 0)) / 2.0,
                    "bearing_deg": float(ell_el.attrib.get("angle", 0)),
                }
            except ValueError:
                # Bad numeric — silently drop the ellipse hint and
                # keep the point.
                out.pop("geometry_kind", None)
                out.pop("ellipse", None)

    # Classify as PLI (position-location-information) so the listener
    # can default-drop these. ATAK EUDs flood the wire with their own
    # PLI at high rate; we don't want one row per ping. Heuristic:
    # `a-f-*-*-U-C-I` is the canonical PLI type chain in MIL-STD-2525
    # (friendly ground unit combat individual).
    if _looks_like_pli(cot_type, detail):
        out["_cot_kind"] = "pli"
    else:
        out["_cot_kind"] = "event"

    return out


def _looks_like_pli(cot_type: str, detail: ET.Element | None) -> bool:
    """PLI events are friendly-affiliation individual unit reports
    (a-f-G-U-C, a-f-G-U-C-I, etc.) and typically carry a __group
    element identifying the team. The single most reliable signal is
    the affiliation+function+modifier prefix."""
    parts = cot_type.split("-")
    is_friendly = len(parts) > 1 and parts[1] == "f"
    is_unit = "U" in parts[2:5] if len(parts) > 2 else False  # noqa: PLR2004 — CoT type structure: index 2+ is the dimension field
    has_group = detail is not None and detail.find("__group") is not None
    return is_friendly and is_unit and has_group


def _parse_cot_dtg(value: str) -> datetime:
    """Parse a CoT timestamp. The standard is ISO 8601 with `Z`
    suffix, but TAK Server tolerates the lazier forms; we accept any
    common shape via fromisoformat after a Z→+00:00 swap."""
    cleaned = value.replace("Z", "+00:00") if value.endswith("Z") else value
    return datetime.fromisoformat(cleaned)


register_source(CotInSource.name, CotInSource)
