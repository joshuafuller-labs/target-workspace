"""Tests for the raw CoT publisher (TDD chunk 8)."""

from __future__ import annotations

import socket
import threading
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from target_workspace.models.target import Target
from target_workspace.plugins.publishers.raw_cot import (
    RawCoTPublisher,
    target_to_cot_xml,
)

pytestmark = [pytest.mark.fast]


def _make_target() -> Target:
    return Target(
        name="BISON-01",
        lat=33.4484,
        lon=-112.0740,
        time=datetime(2026, 5, 16, 21, 45, 0, tzinfo=UTC),
        confidence=0.87,
    )


def test_target_renders_to_valid_cot() -> None:
    xml = target_to_cot_xml(_make_target())
    root = ET.fromstring(xml)
    assert root.tag == "event"
    assert root.attrib["version"] == "2.0"
    point = root.find("point")
    assert point is not None
    assert float(point.attrib["lat"]) == pytest.approx(33.4484)
    assert float(point.attrib["lon"]) == pytest.approx(-112.0740, abs=1e-3)
    contact = root.find("./detail/contact")
    assert contact is not None
    assert contact.attrib["callsign"] == "BISON-01"
    confidence = root.find("./detail/tw_confidence")
    assert confidence is not None
    assert float(confidence.attrib["value"]) == pytest.approx(0.87)


def test_udp_publish_round_trip() -> None:
    """Send a CoT event via the UDP publisher and observe it on a loopback listener."""
    received: list[bytes] = []
    listener = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    listener.bind(("127.0.0.1", 0))
    listener.settimeout(2.0)
    port = listener.getsockname()[1]

    def receive() -> None:
        try:
            data, _addr = listener.recvfrom(8192)
            received.append(data)
        except TimeoutError:
            pass

    t = threading.Thread(target=receive, daemon=True)
    t.start()
    publisher = RawCoTPublisher()
    publisher.publish(
        target=_make_target(),
        adapter_config={"transport": "udp", "host": "127.0.0.1", "port": port},
    )
    t.join(timeout=2.5)
    listener.close()

    assert len(received) == 1
    root = ET.fromstring(received[0])
    assert root.tag == "event"


def test_unknown_transport_raises() -> None:
    publisher = RawCoTPublisher()
    with pytest.raises(ValueError, match="unknown transport"):
        publisher.publish(
            target=_make_target(),
            adapter_config={"transport": "carrier-pigeon", "host": "x", "port": 0},
        )


def test_id_round_trips() -> None:
    target = _make_target()
    object.__setattr__(target, "id", uuid4())
    xml = target_to_cot_xml(target)
    root = ET.fromstring(xml)
    assert root.attrib["uid"] == str(target.id)


def test_remarks_render_in_cot() -> None:
    target = _make_target()
    target.remarks = "Vehicle observed near checkpoint, IR signature."
    xml = target_to_cot_xml(target)
    root = ET.fromstring(xml)
    remarks = root.find("./detail/remarks")
    assert remarks is not None
    assert remarks.text == "Vehicle observed near checkpoint, IR signature."


def test_remarks_omitted_when_blank() -> None:
    target = _make_target()
    target.remarks = None
    xml = target_to_cot_xml(target)
    root = ET.fromstring(xml)
    assert root.find("./detail/remarks") is None


def test_source_renders_attribution_element() -> None:
    target = _make_target()
    target.source = "Ku-band radar DD-3"
    xml = target_to_cot_xml(target)
    root = ET.fromstring(xml)
    src = root.find("./detail/__source")
    assert src is not None
    assert src.attrib["system"] == "Ku-band radar DD-3"


def test_deep_link_appended_to_remarks() -> None:
    target = _make_target()
    target.remarks = "Hostile per RoE."
    board_uuid = uuid4()
    xml = target_to_cot_xml(
        target,
        public_url="https://tw.example.com",
        board_id=str(board_uuid),
    )
    root = ET.fromstring(xml)
    remarks = root.find("./detail/remarks")
    assert remarks is not None
    assert remarks.text is not None
    assert "Hostile per RoE." in remarks.text
    assert "Open in Target Workspace:" in remarks.text
    assert f"https://tw.example.com/boards/{board_uuid}#target/{target.id}" in remarks.text


def test_deep_link_alone_when_no_user_remarks() -> None:
    """When the operator hasn't written remarks but a deep-link is available,
    publish the link by itself so the round-trip still works."""
    target = _make_target()
    target.remarks = None
    board_uuid = uuid4()
    xml = target_to_cot_xml(
        target,
        public_url="https://tw.example.com",
        board_id=str(board_uuid),
    )
    root = ET.fromstring(xml)
    remarks = root.find("./detail/remarks")
    assert remarks is not None
    assert remarks.text is not None
    assert remarks.text.startswith("Open in Target Workspace:")


def test_ellipse_geometry_emits_ellipse_detail() -> None:
    """An ellipse target adds <ellipse major minor angle/> to detail."""
    from target_workspace.models.target import Ellipse

    target = Target(
        name="DF-CONE-09",
        lat=33.4484,
        lon=-112.0740,
        time=datetime(2026, 5, 16, 21, 45, 0, tzinfo=UTC),
        geometry_kind="ellipse",
        ellipse=Ellipse(semi_major_m=1500.0, semi_minor_m=300.0, bearing_deg=87.5),
    )
    xml = target_to_cot_xml(target)
    root = ET.fromstring(xml)
    el = root.find("./detail/ellipse")
    assert el is not None
    # TAK convention publishes full-axis lengths, not semi-axes
    assert float(el.attrib["major"]) == pytest.approx(3000.0)
    assert float(el.attrib["minor"]) == pytest.approx(600.0)
    assert float(el.attrib["angle"]) == pytest.approx(87.5)
    # Point element still present as anchor
    assert root.find("point") is not None


def test_polygon_geometry_emits_polygon_with_vertices() -> None:
    target = Target(
        name="AREA-44",
        lat=33.4450,
        lon=-112.0750,
        time=datetime(2026, 5, 16, 21, 45, 0, tzinfo=UTC),
        geometry_kind="polygon",
        polygon_vertices=[
            [33.4500, -112.0800],
            [33.4500, -112.0700],
            [33.4400, -112.0700],
            [33.4400, -112.0800],
        ],
    )
    xml = target_to_cot_xml(target)
    root = ET.fromstring(xml)
    poly = root.find("./detail/__polygon")
    assert poly is not None
    verts = poly.findall("vertex")
    assert len(verts) == 4
    assert float(verts[0].attrib["lat"]) == pytest.approx(33.4500)
    assert float(verts[2].attrib["lon"]) == pytest.approx(-112.0700)
    # Point element still present as anchor
    assert root.find("point") is not None


def test_point_geometry_skips_shape_extensions() -> None:
    """A plain point target (the default) emits no ellipse or polygon."""
    target = _make_target()  # geometry_kind defaults to point
    xml = target_to_cot_xml(target)
    root = ET.fromstring(xml)
    assert root.find("./detail/ellipse") is None
    assert root.find("./detail/__polygon") is None
