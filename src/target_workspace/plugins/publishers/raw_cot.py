"""Raw CoT Publisher — emits CoT XML over UDP or TCP.

Lowest-common-denominator publisher; drops directly into ATAK EUDs or any
CoT consumer with no TAK Server in between. Configuration:

  adapter_config = {
      "transport": "udp" | "tcp",
      "host": "239.2.3.1" | "10.10.10.5",
      "port": 6969,
  }

If the publisher cannot reach the configured endpoint, the workflow
engine treats the failure as non-fatal and records an `updated` audit
event noting the dispatch failure.
"""

from __future__ import annotations

import socket

# ET builds CoT XML (Element/SubElement) and never parses untrusted input, so
# defusedxml doesn't apply — suppress semgrep's use-defused-xml on this import.
import xml.etree.ElementTree as ET  # nosemgrep
from datetime import UTC, datetime, timedelta
from typing import Any

from target_workspace.brand import BRAND_NAME
from target_workspace.plugins.loader import register_publisher


def _format_dtg(dt: datetime) -> str:
    """ISO-8601 UTC with trailing Z, the CoT convention."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def target_to_cot_xml(
    target: Any,
    *,
    public_url: str | None = None,
    board_id: str | None = None,
) -> bytes:
    """Render a Target as a minimal CoT 2.0 event element.

    Optional `public_url` + `board_id` cause a deep-link line to be
    appended to the <remarks> element so a TAK EUD can tap and round-trip
    back to the SPA card.
    """
    now = datetime.now(tz=UTC)
    stale = target.stale or (now + timedelta(minutes=15))
    event = ET.Element(
        "event",
        attrib={
            "version": "2.0",
            "uid": str(target.id),
            "type": target.cot_type,
            "time": _format_dtg(now),
            "start": _format_dtg(target.time),
            "stale": _format_dtg(stale),
            "how": "h-g-i-g-o",  # human, gps, intentional, generic, other
        },
    )
    point = ET.SubElement(
        event,
        "point",
        attrib={
            "lat": f"{target.lat:.7f}",
            "lon": f"{target.lon:.7f}",
            "hae": f"{target.hae or 0.0:.1f}",
            "ce": f"{target.ce or 9999999.0:.1f}",
            "le": f"{target.le or 9999999.0:.1f}",
        },
    )
    _ = point  # silence unused-name; ET adds it to event tree
    detail = ET.SubElement(event, "detail")
    ET.SubElement(detail, "contact", attrib={"callsign": target.name})
    if target.confidence is not None:
        ET.SubElement(detail, "tw_confidence", attrib={"value": f"{target.confidence:.2f}"})
    # Attribution: <__source system="..."/> when target.source is set.
    source = getattr(target, "source", None)
    if source:
        ET.SubElement(detail, "__source", attrib={"system": str(source)})
    # Geometry beyond point — TAK convention is to keep <point> as the
    # anchor and add a detail extension carrying the shape parameters.
    geometry_kind = getattr(target, "geometry_kind", "point")
    if geometry_kind == "ellipse" and getattr(target, "ellipse", None) is not None:
        e = target.ellipse
        ET.SubElement(
            detail,
            "ellipse",
            attrib={
                # TAK's "major"/"minor" are diameters in meters; we store
                # semi-axes, so multiply by 2 to publish the full axis.
                "major": f"{e.semi_major_m * 2:.2f}",
                "minor": f"{e.semi_minor_m * 2:.2f}",
                "angle": f"{e.bearing_deg:.2f}",
            },
        )
    elif geometry_kind == "polygon" and getattr(target, "polygon_vertices", None):
        # Use a __polygon extension element with <vertex lat lon/> children
        # — keeps the wire format self-describing without committing us to
        # one specific TAK polygon dialect (CoT/TAK supports several).
        poly = ET.SubElement(detail, "__polygon")
        for lat, lon in target.polygon_vertices:
            ET.SubElement(poly, "vertex", attrib={"lat": f"{lat:.7f}", "lon": f"{lon:.7f}"})
    # Remarks: user-authored note, optionally appended with a deep-link
    # back to the SPA card so an ATAK operator can tap and round-trip.
    remarks_text = getattr(target, "remarks", None) or ""
    if public_url and board_id:
        link = f"{public_url.rstrip('/')}/boards/{board_id}#target/{target.id}"
        deep_link = f"Open in {BRAND_NAME}: {link}"
        remarks_text = f"{remarks_text}\n\n{deep_link}".strip() if remarks_text else deep_link
    if remarks_text:
        remarks_el = ET.SubElement(detail, "remarks")
        remarks_el.text = remarks_text
    rendered: bytes = ET.tostring(event, encoding="utf-8")
    return rendered


class RawCoTPublisher:
    name = "raw_cot"

    def publish(self, *, target: Any, adapter_config: dict[str, Any]) -> None:
        transport = str(adapter_config.get("transport", "udp")).lower()
        host = str(adapter_config.get("host", "127.0.0.1"))
        port = int(adapter_config.get("port", 6969))
        public_url = adapter_config.get("public_url")
        board_id = adapter_config.get("board_id")
        payload = target_to_cot_xml(
            target,
            public_url=str(public_url) if public_url else None,
            board_id=str(board_id) if board_id else None,
        )

        if transport == "udp":
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                # Multicast-friendly default TTL (configurable later).
                s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 8)
                s.sendto(payload, (host, port))
        elif transport == "tcp":
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(5.0)
                s.connect((host, port))
                s.sendall(payload + b"\n")
        else:
            msg = f"unknown transport: {transport!r}"
            raise ValueError(msg)


register_publisher(RawCoTPublisher.name, RawCoTPublisher)
