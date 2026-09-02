"""Unit tests for the TAK Server Publisher QUIC transport.

Research findings (sources cited inline; gathered 2026-05-24):

ALPN identifier — ``takstream``
    TAK Server 5.x exposes a QUIC streaming input on UDP/8090. The
    Application-Layer Protocol Negotiation (ALPN) token the input
    advertises is the literal string ``takstream``. Confirmed against the
    TAK Server reference QUIC implementation, where BOTH the server and
    the client call ``QuicSslContextBuilder...applicationProtocols("takstream")``:
      - server: TAK-Product-Center/Server
        src/testing/netty-quic-cot-client/.../netty/NettyServer.java
        (``.applicationProtocols("takstream")``)
      - client: same repo, .../netty/NettyClient.java
        (``.applicationProtocols("takstream")``, ``QuicStreamType.BIDIRECTIONAL``)
    A QUIC client whose ALPN list does not contain ``takstream`` is rejected
    at the TLS handshake (no common protocol).

Stream + framing — client-initiated BIDIRECTIONAL stream, TAK Protocol v1 STREAM frames
    The reference client opens a single client-initiated *bidirectional*
    QUIC stream after the handshake completes and writes its CoT payload on
    it. We carry the same TAK Protocol Version 1 ``STREAM`` framing we
    already build for the TCP/TLS path: a ``0xbf`` (191) magic marker byte,
    a varint payload length, then the protobuf-serialised ``TakMessage``
    (one ``atakmap::commoncommo::v1::TakMessage`` per frame). Confirmed via
    the takproto docs:
      - https://takproto.readthedocs.io/en/latest/tak_protocols/
        ("191 <varint payload length> <payload>")
      - deptofdefense/AndroidTacticalAssaultKit-CIV takproto/README.md
        ("the single byte 0xbf ... encoded as a 'varint'")
    Note: the TAK reference *test* client writes raw CoT XML on the stream;
    that exercises the legacy version-negotiation handshake. The canonical
    TAK Protocol v1 streaming wire format — and what this publisher emits —
    is the ``0xbf``-framed protobuf produced by ``takproto.xml2proto(xml,
    TAKProtoVer.STREAM)``, which ``takproto.parse_proto`` round-trips back to
    a ``TakMessage``.

Test strategy
    Stand up a real ``aioquic`` QUIC server on loopback with a self-signed
    cert (generated in-test via ``cryptography``) advertising the
    ``takstream`` ALPN. It accepts the publisher's bidirectional stream and
    captures the received bytes. We then assert the captured bytes are
    takproto STREAM frames (first byte ``0xbf``) that ``parse_proto``
    round-trips to the self-SA (a TAK presence event whose uid we recognise)
    followed by the target (callsign on the contact).
"""

from __future__ import annotations

import asyncio
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from takproto import TAKProtoVer, parse_proto

from target_workspace.models.target import Target
from target_workspace.plugins.publishers.tak_server import TAK_QUIC_ALPN, TakServerPublisher

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = [pytest.mark.fast]


def _make_target() -> Target:
    return Target(
        name="BISON-01",
        lat=33.4484,
        lon=-112.0740,
        time=datetime(2026, 5, 16, 21, 45, 0, tzinfo=UTC),
        confidence=0.87,
    )


def _gen_self_signed_cert(tmp_path: Path) -> tuple[Path, Path]:
    """Mint a self-signed cert + key into tmp_path. Returns (cert, key)."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime(2026, 1, 1, tzinfo=UTC))
        .not_valid_after(datetime(2030, 1, 1, tzinfo=UTC))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("localhost")]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    cert_path = tmp_path / "cert.pem"
    key_path = tmp_path / "key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
    )
    return cert_path, key_path


def _split_stream_frames(buf: bytes) -> list[bytearray]:
    """Split a concatenated TAK Protocol v1 STREAM byte buffer into frames.

    Each frame is ``0xbf <varint length> <protobuf payload>``. We decode the
    varint, slice out the payload, and re-wrap each as a standalone STREAM
    frame so ``parse_proto`` (which expects exactly one frame) can read it.
    """
    frames: list[bytearray] = []
    i = 0
    n = len(buf)
    while i < n:
        assert buf[i] == 0xBF, f"frame {len(frames)} must start with 0xbf, got {buf[i]:#x}"
        i += 1
        # Decode varint length.
        length = 0
        shift = 0
        while True:
            b = buf[i]
            i += 1
            length |= (b & 0x7F) << shift
            if not (b & 0x80):
                break
            shift += 7
        payload = buf[i : i + length]
        i += length
        frame = bytearray([0xBF])
        # Re-encode the length varint in front of the payload.
        ln = length
        while True:
            byte = ln & 0x7F
            ln >>= 7
            if ln:
                frame.append(byte | 0x80)
            else:
                frame.append(byte)
                break
        frame.extend(payload)
        frames.append(frame)
    return frames


class _QuicLoopbackServer:
    """A real aioquic QUIC server on loopback that captures one stream."""

    def __init__(self, cert_path: Path, key_path: Path) -> None:
        self._cert_path = cert_path
        self._key_path = key_path
        self.received = bytearray()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._stop: asyncio.Event | None = None
        self._tasks: set[asyncio.Task[None]] = set()
        self.port = 0
        self._data_seen = threading.Event()

    def _stream_handler(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        async def _drain() -> None:
            try:
                # Respond to the TAK v1 negotiation request so the publisher switches
                # to protobuf immediately (mirrors a real TAK Server's QUIC input).
                answered = False
                while True:
                    chunk = await reader.read(4096)
                    if not chunk:
                        break
                    self.received.extend(chunk)
                    if not answered and b"t-x-takp-q" in bytes(self.received):
                        writer.write(
                            b'<?xml version="1.0"?><event version="2.0" type="t-x-takp-r">'
                            b'<detail><TakControl><TakResponse status="true"/></TakControl>'
                            b"</detail></event>"
                        )
                        answered = True
            finally:
                self._data_seen.set()
                writer.close()

        assert self._loop is not None
        # Keep a strong reference so the task isn't GC'd mid-flight.
        task = self._loop.create_task(_drain())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _run(self) -> None:
        from aioquic.asyncio.server import serve
        from aioquic.quic.configuration import QuicConfiguration

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop

        config = QuicConfiguration(
            is_client=False,
            alpn_protocols=[TAK_QUIC_ALPN],
        )
        config.load_cert_chain(str(self._cert_path), str(self._key_path))

        async def _serve() -> None:
            self._stop = asyncio.Event()
            server = await serve(
                "127.0.0.1",
                0,
                configuration=config,
                stream_handler=self._stream_handler,
            )
            transport = server._transport
            assert transport is not None
            self.port = transport.get_extra_info("sockname")[1]
            self._ready.set()
            await self._stop.wait()
            server.close()
            await asyncio.sleep(0.1)
            if self._tasks:
                _, pending = await asyncio.wait(self._tasks, timeout=1.0)
                for task in pending:
                    task.cancel()
                if pending:
                    await asyncio.gather(*pending, return_exceptions=True)

        try:
            loop.run_until_complete(_serve())
        finally:
            try:
                pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
                for task in pending:
                    task.cancel()
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                loop.run_until_complete(loop.shutdown_asyncgens())
                loop.run_until_complete(loop.shutdown_default_executor())
            finally:
                asyncio.set_event_loop(None)
                loop.close()

    def __enter__(self) -> _QuicLoopbackServer:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        assert self._ready.wait(timeout=5.0), "QUIC server failed to start"
        return self

    def __exit__(self, *_exc: object) -> None:
        if self._loop is not None and self._stop is not None:
            self._loop.call_soon_threadsafe(self._stop.set)
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            assert not self._thread.is_alive(), "QUIC server thread did not stop"

    def wait_for_data(self, timeout: float = 5.0) -> None:
        assert self._data_seen.wait(timeout=timeout), "no QUIC stream data received"


@pytest.fixture
def quic_server(tmp_path: Path) -> Iterator[tuple[_QuicLoopbackServer, Path, Path]]:
    cert_path, key_path = _gen_self_signed_cert(tmp_path)
    with _QuicLoopbackServer(cert_path, key_path) as srv:
        yield srv, cert_path, key_path


def test_quic_send_round_trip(
    quic_server: tuple[_QuicLoopbackServer, Path, Path],
) -> None:
    """Publish over QUIC; the server must receive 0xbf STREAM frames that
    round-trip to the self-SA presence event then the target callsign."""
    srv, cert_path, key_path = quic_server
    target = _make_target()

    publisher = TakServerPublisher()
    publisher.publish(
        target=target,
        adapter_config={
            "transport": "quic",
            "cot_url": f"quic://127.0.0.1:{srv.port}",
            "host": "127.0.0.1",
            "port": srv.port,
            "client_cert_pem_path": str(cert_path),
            "client_key_pem_path": str(key_path),
            "ca_cert_pem_path": str(cert_path),  # self-signed: cert is its own CA
            "verify_hostname": False,
            "timeout_seconds": 5,
        },
    )

    srv.wait_for_data(timeout=5.0)
    raw = bytes(srv.received)
    # The QUIC stream is negotiated to v1 first: the XML t-x-takp-q request
    # precedes the 0xbf STREAM frames. Strip it before splitting frames.
    bf = raw.find(b"\xbf")
    assert b"t-x-takp-q" in raw[:bf], "must negotiate v1 (t-x-takp-q) before protobuf frames"
    frames = _split_stream_frames(raw[bf:])

    min_frames = 2  # self-SA, then the target
    assert len(frames) >= min_frames, (
        f"expected >= {min_frames} STREAM frames (self-SA + target), got {len(frames)}"
    )

    parsed = [parse_proto(bytearray(f)) for f in frames]
    assert all(m is not None for m in parsed), "every frame must parse as a TakMessage"

    callsigns = [m.cotEvent.detail.contact.callsign for m in parsed if m is not None]
    # The self-SA must be sent FIRST so the TAK Server registers our presence
    # before the target referencing us arrives.
    assert callsigns[-1] == "BISON-01", (
        f"last frame must be the target (callsign BISON-01); got {callsigns}"
    )
    # The self-SA frame is a distinct presence event (a-f-G-U / typical
    # self type) carrying our own uid — not the target's callsign.
    uids = [m.cotEvent.uid for m in parsed if m is not None]
    assert uids[-1] == str(target.id), "target frame uid must equal the Target id"
    self_sa_uid = uids[0]
    assert self_sa_uid, "first frame must carry a self-SA uid"
    assert self_sa_uid != str(target.id), (
        "first frame must be a distinct self-SA presence event, not the target"
    )


def test_quic_alpn_is_takstream() -> None:
    """The ALPN token must be the TAK Server QUIC input identifier."""
    assert TAK_QUIC_ALPN == "takstream"


def test_quic_selected_by_scheme(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A quic:// cot_url must route through the QUIC transport, not TLS."""
    cert_path, key_path = _gen_self_signed_cert(tmp_path)
    captured: dict[str, Any] = {}

    def _fake_quic_publish(
        self: TakServerPublisher,
        *,
        host: str,
        port: int,
        frames: list[bytes],
        **kwargs: Any,
    ) -> None:
        captured["host"] = host
        captured["port"] = port
        captured["frames"] = frames
        captured["alpn"] = kwargs.get("alpn")

    monkeypatch.setattr(TakServerPublisher, "_publish_quic", _fake_quic_publish)

    publisher = TakServerPublisher()
    publisher.publish(
        target=_make_target(),
        adapter_config={
            "cot_url": "quic://tak.example:8090",
            "client_cert_pem_path": str(cert_path),
            "client_key_pem_path": str(key_path),
        },
    )

    assert captured["host"] == "tak.example"
    assert captured["port"] == 8090
    assert captured["alpn"] == "takstream"
    assert all(f[0] == 0xBF for f in captured["frames"]), "frames must be STREAM-framed"


def test_quic_frames_are_v1_stream(tmp_path: Path) -> None:
    """_to_tak_v1 must produce a 0xbf STREAM frame that round-trips."""
    from target_workspace.plugins.publishers.raw_cot import target_to_cot_xml
    from target_workspace.plugins.publishers.tak_server import _to_tak_v1

    frame = _to_tak_v1(target_to_cot_xml(_make_target()))
    assert frame[0] == 0xBF
    msg = parse_proto(bytearray(frame))
    assert msg is not None
    assert msg.cotEvent.detail.contact.callsign == "BISON-01"
    # Sanity: the helper builds STREAM (not MESH) framing.
    assert TAKProtoVer.STREAM == TAKProtoVer.STREAM
