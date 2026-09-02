"""TDD: protobuf streaming must negotiate TAK Protocol v1 before sending.

A coreVersion=2 TAK streaming connection starts in XML (v0). Raw 0xbf STREAM
frames sent without a successful version negotiation are parsed as XML and
silently dropped (confirmed live against a real TAK Server). So in protobuf
mode the publisher must send the ``t-x-takp-q`` request and wait for the
server's response BEFORE emitting any 0xbf frame.
"""

from __future__ import annotations

import socket
import threading
from datetime import UTC, datetime

import pytest

from target_workspace.models.target import Target
from target_workspace.plugins.publishers.tak_server import TakServerPublisher

pytestmark = [pytest.mark.fast]

_TAK_RESPONSE = (
    b'<?xml version="1.0"?><event version="2.0" uid="takproto-negotiation" '
    b'type="t-x-takp-r" how="m-g" time="2026-05-16T21:45:00.000Z" '
    b'start="2026-05-16T21:45:00.000Z" stale="2026-05-16T21:50:00.000Z">'
    b'<point lat="0" lon="0" hae="0" ce="9999999" le="9999999"/>'
    b'<detail><TakControl><TakResponse status="true"/></TakControl></detail></event>'
)


class _NegotiatingEndpoint:
    """TCP stand-in for a TAK Server that answers the v1 negotiation request."""

    def __init__(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(1)
        self.port: int = self._sock.getsockname()[1]
        self.data: bytes = b""
        self.done = threading.Event()
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
                    if not answered and b"t-x-takp-q" in self.data:
                        conn.sendall(_TAK_RESPONSE)
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


def test_protobuf_mode_negotiates_before_sending_frames() -> None:
    ep = _NegotiatingEndpoint()
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
        assert ep.wait(), "negotiating endpoint did not finish reading publisher stream"
    finally:
        ep.stop()

    data = ep.data
    q = data.find(b"t-x-takp-q")
    bf = data.find(b"\xbf")
    assert q != -1, f"negotiation request must be sent first; got {data[:120]!r}"
    assert bf != -1, "protobuf STREAM frames must follow the negotiation"
    assert q < bf, "the negotiation request must precede the first 0xbf frame"
    # the negotiated protobuf stream still carries the target
    assert b"HOSTILE-ALPHA" in data
    assert b"<event" in data[:bf], "pre-protobuf bytes are the XML negotiation request"
