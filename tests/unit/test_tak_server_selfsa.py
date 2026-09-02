"""TDD (tw-takv-selfsa): the TAK-server publisher must register an EUD.

A real TAK Server (e.g. OpenTAK Server) will not store a target's CoT
unless it arrives from a *registered* EUD over a live stream — it
enforces `cot.sender_uid -> euds` and expects a self-SA (the client's
own "a-f-*" situational-awareness event) first. The legacy publisher
sent only the target and closed, so OTS dropped it (FK violation).

Contract pinned here (transport-agnostic, captured at the TCP layer):
  1. On publish, the publisher sends a self-SA announcing the configured
     EUD identity (friendly `a-f-*`, our uid + callsign), THEN
  2. the target's CoT,
  both over a single connection to the configured `cot_url`.
"""

from __future__ import annotations

import socket
import threading
import xml.etree.ElementTree as ET
from datetime import UTC, datetime

import pytest

from target_workspace.models.target import Target
from target_workspace.plugins.publishers.tak_server import TakServerPublisher

pytestmark = [pytest.mark.fast]


class _CaptureEndpoint:
    """Threaded TCP server standing in for a TAK Server; captures the
    full byte stream the publisher sends over one connection."""

    def __init__(self, *, respond_negotiation: bool = False) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(1)
        self.port: int = self._sock.getsockname()[1]
        self.data: bytes = b""
        self.done = threading.Event()
        self._respond_negotiation = respond_negotiation
        self._thread = threading.Thread(target=self._serve, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def _serve(self) -> None:
        self._sock.settimeout(5)
        try:
            conn, _ = self._sock.accept()
        except OSError:
            self.done.set()
            return
        conn.settimeout(3)
        answered = False
        try:
            with conn:
                while True:
                    try:
                        chunk = conn.recv(4096)
                    except OSError:
                        break
                    if not chunk:
                        break
                    self.data += chunk
                    if self._respond_negotiation and not answered and b"t-x-takp-q" in self.data:
                        conn.sendall(
                            b'<?xml version="1.0"?><event version="2.0" type="t-x-takp-r">'
                            b'<detail><TakControl><TakResponse status="true"/></TakControl>'
                            b"</detail></event>"
                        )
                        answered = True
        finally:
            self.done.set()

    def wait(self, timeout: float = 2.0) -> bool:
        return self.done.wait(timeout)

    def stop(self) -> None:
        self._sock.close()
        self._thread.join(timeout=1)


def _target() -> Target:
    return Target(
        name="HOSTILE-ALPHA",
        cot_type="a-h-G-U-C-I",
        lat=34.0522,
        lon=-112.2437,
        time=datetime(2026, 5, 16, 21, 45, 0, tzinfo=UTC),
        confidence=0.9,
    )


def _events(raw: bytes) -> list[ET.Element]:
    text = raw.decode("utf-8", "ignore")
    out: list[ET.Element] = []
    for frag in text.split("</event>"):
        if "<event" in frag:
            start = frag.index("<event")
            out.append(ET.fromstring(frag[start:] + "</event>"))
    return out


def test_publish_sends_self_sa_then_target_over_one_stream() -> None:
    ep = _CaptureEndpoint()
    ep.start()

    try:
        TakServerPublisher().publish(
            target=_target(),
            adapter_config={
                "cot_url": f"tcp://127.0.0.1:{ep.port}",
                "eud_uid": "TW-PUBLISHER-EUD",
                "eud_callsign": "TARGET-WORKBENCH",
                "eud_register_grace_seconds": 0,
                "post_send_hold_seconds": 0,
            },
        )
        assert ep.wait(), "capture endpoint did not finish reading publisher stream"
    finally:
        ep.stop()

    events = _events(ep.data)
    assert len(events) >= 2, f"expected self-SA + target; captured: {ep.data[:300]!r}"

    self_sa, target = events[0], events[1]
    # 1) self-SA registers our EUD: friendly affiliation, our uid + callsign
    assert self_sa.attrib["uid"] == "TW-PUBLISHER-EUD"
    assert self_sa.attrib["type"].startswith("a-f-"), self_sa.attrib["type"]
    contact = self_sa.find(".//contact")
    assert contact is not None and contact.attrib.get("callsign") == "TARGET-WORKBENCH"

    # 2) the target CoT follows, on the same stream
    assert target.attrib["type"] == "a-h-G-U-C-I"
    tcontact = target.find(".//contact")
    assert tcontact is not None and tcontact.attrib.get("callsign") == "HOSTILE-ALPHA"


def test_protobuf_mode_sends_tak_v1_stream_frames() -> None:
    """protocol='protobuf' negotiates TAK Protocol v1 (sends the XML
    ``t-x-takp-q`` request first) and THEN emits takproto STREAM frames —
    magic byte 0xbf + varint length + protobuf TakMessage — which round-trip
    to the self-SA EUD and carry the target."""
    import takproto

    ep = _CaptureEndpoint(respond_negotiation=True)
    ep.start()

    try:
        TakServerPublisher().publish(
            target=_target(),
            adapter_config={
                "cot_url": f"tcp://127.0.0.1:{ep.port}",
                "eud_uid": "TW-PUBLISHER-EUD",
                "eud_callsign": "TARGET-WORKBENCH",
                "protocol": "protobuf",
                "eud_register_grace_seconds": 0,
                "post_send_hold_seconds": 0,
            },
        )
        assert ep.wait(), "capture endpoint did not finish reading protobuf stream"
    finally:
        ep.stop()

    data = ep.data
    # The v1 negotiation request (XML) precedes the first 0xbf STREAM frame.
    q = data.find(b"t-x-takp-q")
    bf = data.find(b"\xbf")
    assert q != -1 and bf != -1 and q < bf, f"negotiation must precede protobuf; got {data[:80]!r}"
    # The protobuf after negotiation round-trips to the self-SA EUD.
    first = takproto.parse_proto(bytearray(data[bf:]))
    assert first is not None and first.cotEvent.uid == "TW-PUBLISHER-EUD"
    # Both callsigns appear inline in the protobuf stream.
    assert b"TARGET-WORKBENCH" in data and b"HOSTILE-ALPHA" in data
