"""TAK Server Publisher — CoT to a TAK Server.

Two transports, selected by adapter_config:

  * **pytak stream** (set ``cot_url`` = ``tcp://host:8088`` or
    ``tls://host:8089``): registers our EUD via a self-SA, then streams the
    target on the same connection. This is the lifecycle a real TAK Server
    (e.g. OpenTAK Server) requires before it will accept and store a target —
    OTS enforces ``cot.sender_uid -> euds``, so the self-SA must arrive first.

  * **legacy stdlib mTLS** (set ``host`` + ``client_cert_pem_path`` /
    ``client_key_pem_path``, no ``cot_url``): one CoT over a client-cert TLS
    socket. Retained for existing deployments.

Wire format is the same CoT XML produced by the raw_cot publisher
(``target_to_cot_xml``) — same remarks deep-link, ``__source`` attribution,
ellipse / ``__polygon`` detail extensions. Only the transport differs.

Configuration (adapter_config):
    {
        # --- pytak stream (real TAK Server / OpenTAK Server) ---
        "cot_url":      "tcp://tak.example.com:8088",  # or tls://...:8089
        "eud_uid":      "tw-publisher-eud",            # our EUD identity (self-SA)
        "eud_callsign": "TARGET-WORKBENCH",            # self-SA callsign
        # --- legacy stdlib mTLS (no cot_url) ---
        "host": "tak.example.com", "port": 8089,
        "client_cert_pem_path": "/etc/tak/client.pem",
        "client_key_pem_path":  "/etc/tak/client.key",
        "ca_cert_pem_path":     "/etc/tak/ca.pem",     # optional
        # --- common ---
        "verify_hostname": true, "timeout_seconds": 10,
        "eud_register_grace_seconds": 0.15,            # optional stream tuning
        "post_send_hold_seconds": 2.0,                 # optional stream tuning
        "public_url": "https://tw.example",            # deep-link prefix
        # board_id is injected by the workflow engine at publish time
    }

Best-effort: handshake/socket errors propagate; the workflow engine treats
them as non-fatal and records an `updated` audit event with the failure.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import socket
import ssl
import tempfile

# ET builds the self-SA CoT only (never parses untrusted input) → defusedxml
# (a parser) doesn't apply; suppress semgrep's use-defused-xml on this import.
import xml.etree.ElementTree as ET  # nosemgrep
from configparser import ConfigParser
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlsplit

import defusedxml.ElementTree as DET
import httpx
from defusedxml import DefusedXmlException

from target_workspace.plugins.loader import register_publisher
from target_workspace.plugins.publishers.raw_cot import _format_dtg, target_to_cot_xml

# A self-SA is short-lived presence; 5 min is the ATAK default cadence ballpark.
_SELF_SA_STALE_MINUTES = 5
# Small pause after the self-SA so the server can register the EUD before the
# target arrives. Kept short — a long idle gap trips a TAK server's read
# timeout and drops the connection before the target is sent.
_EUD_REGISTER_GRACE_S = 0.15
# Hold the connection open briefly after the last frame so the server reads and
# processes it before we close (avoids a "no data / closing" race).
_POST_SEND_HOLD_S = 2.0
# Max wait for the server's TAK version-negotiation response before sending
# protobuf frames. Real servers respond in milliseconds.
_NEGOTIATION_RESPONSE_TIMEOUT_S = 3.0


def _stream_delay_config(cfg: dict[str, Any]) -> tuple[float, float]:
    return (
        float(cfg.get("eud_register_grace_seconds", _EUD_REGISTER_GRACE_S)),
        float(cfg.get("post_send_hold_seconds", _POST_SEND_HOLD_S)),
    )


def _self_sa_xml(*, eud_uid: str, callsign: str, lat: float, lon: float) -> bytes:
    """Build a friendly self-SA CoT so the TAK server registers our EUD.

    Mirrors an ATAK client's identity beacon (``a-f-G-U-C`` with takv +
    contact + group) — enough for a TAK Server to create the EUD row that
    subsequent target CoT is attributed to.
    """
    now = datetime.now(tz=UTC)
    evt = ET.Element(
        "event",
        {
            "version": "2.0",
            "uid": eud_uid,
            "type": "a-f-G-U-C",
            "how": "m-g",
            "time": _format_dtg(now),
            "start": _format_dtg(now),
            "stale": _format_dtg(now + timedelta(minutes=_SELF_SA_STALE_MINUTES)),
        },
    )
    ET.SubElement(
        evt,
        "point",
        {
            "lat": f"{lat:.7f}",
            "lon": f"{lon:.7f}",
            "hae": "9999999.0",
            "ce": "9999999.0",
            "le": "9999999.0",
        },
    )
    detail = ET.SubElement(evt, "detail")
    ET.SubElement(
        detail,
        "takv",
        {
            "os": "linux",
            "version": "1.0",
            "device": "target-workspace",
            "platform": "target-workspace",
        },
    )
    ET.SubElement(detail, "contact", {"callsign": callsign, "endpoint": "*:-1:stcp"})
    ET.SubElement(detail, "uid", {"Droid": callsign})
    ET.SubElement(detail, "__group", {"name": "Cyan", "role": "Team Member"})
    ET.SubElement(detail, "status", {"battery": "100"})
    return ET.tostring(evt)


# Protocol modes: XML (TAK Protocol v0, what OpenTAK Server + legacy clients
# speak) and protobuf (v1, the modern TAK Server / ATAK wire format).
_PROTOBUF_MODES = frozenset({"protobuf", "stream", "v1", "proto"})

# TAK Protocol over QUIC: the TAK Server QUIC input (UDP, default 8090) advertises
# this ALPN; the framing on the client-initiated bidi stream is the same takproto
# STREAM form (0xbf + varint + protobuf TakMessage) used on TLS after negotiation.
TAK_QUIC_ALPN = "takstream"
TAK_QUIC_DEFAULT_PORT = 8090


def _to_tak_v1(cot_xml: bytes) -> bytes:
    """Convert a CoT XML frame to a TAK Protocol v1 STREAM frame.

    STREAM framing is `0xbf <varint length> <protobuf TakMessage>` — the
    length-prefixed form a TAK Server expects on a TCP/TLS stream.
    """
    import takproto  # noqa: PLC0415 — only the protobuf transport needs takproto

    return bytes(takproto.xml2proto(cot_xml.decode("utf-8"), takproto.TAKProtoVer.STREAM))


def _negotiation_request_xml() -> bytes:
    """Build the TAK Protocol version-negotiation request (``t-x-takp-q``).

    Asks the server to switch the stream from XML (v0) to protobuf (v1). The
    server replies with a ``t-x-takp-r`` ``TakResponse``.
    """
    now = datetime.now(tz=UTC)
    evt = ET.Element(
        "event",
        {
            "version": "2.0",
            "uid": "takproto-negotiation",
            "type": "t-x-takp-q",
            "how": "m-g",
            "time": _format_dtg(now),
            "start": _format_dtg(now),
            "stale": _format_dtg(now + timedelta(minutes=_SELF_SA_STALE_MINUTES)),
        },
    )
    ET.SubElement(
        evt, "point", {"lat": "0.0", "lon": "0.0", "hae": "0", "ce": "9999999", "le": "9999999"}
    )
    control = ET.SubElement(ET.SubElement(evt, "detail"), "TakControl")
    ET.SubElement(control, "TakRequest", {"version": "1"})
    return ET.tostring(evt)


async def _negotiate_v1(reader: Any, writer: Any) -> None:
    """Send the v1 negotiation request and wait (briefly) for the response."""
    writer.write(_negotiation_request_xml())
    await writer.drain()
    with contextlib.suppress(Exception):
        async with asyncio.timeout(_NEGOTIATION_RESPONSE_TIMEOUT_S):
            buf = b""
            while b"takp-r" not in buf and b"TakResponse" not in buf:
                chunk = await reader.read(4096)
                if not chunk:
                    break
                buf += chunk


async def _open_stream_connection(cot_url: str, config: ConfigParser) -> tuple[Any, Any]:
    if cot_url.startswith("tcp://"):
        parsed = urlsplit(cot_url)
        if not parsed.hostname:
            msg = "tak_server publisher requires a host in `cot_url`"
            raise ValueError(msg)
        return await asyncio.open_connection(parsed.hostname, parsed.port or 8088)

    import pytak  # noqa: PLC0415 — TLS/UDP/file transports use pytak's factory

    return cast(tuple[Any, Any], await pytak.protocol_factory(config["tak"]))


async def _stream(
    cot_url: str, cfg: dict[str, Any], frames: list[bytes], *, negotiate: bool = False
) -> None:
    """Open a pytak connection to `cot_url` and write `frames` in order.

    When ``negotiate`` is set, run the TAK Protocol version handshake first:
    a coreVersion=2 streaming connection starts in XML (v0) and only accepts
    protobuf (v1) STREAM frames after a successful negotiation, otherwise the
    server parses the 0xbf bytes as XML and silently drops them.
    """
    config = ConfigParser()
    section: dict[str, str] = {"COT_URL": cot_url}
    if cot_url.startswith("tls"):
        if cfg.get("client_cert_pem_path"):
            section["PYTAK_TLS_CLIENT_CERT"] = str(cfg["client_cert_pem_path"])
        if cfg.get("client_key_pem_path"):
            section["PYTAK_TLS_CLIENT_KEY"] = str(cfg["client_key_pem_path"])
        if cfg.get("ca_cert_pem_path"):
            section["PYTAK_TLS_CLIENT_CAFILE"] = str(cfg["ca_cert_pem_path"])
        if not bool(cfg.get("verify_hostname", True)):
            section["PYTAK_TLS_DONT_CHECK_HOSTNAME"] = "1"
    config["tak"] = section

    connect_timeout = float(cfg.get("timeout_seconds", 10))
    async with asyncio.timeout(connect_timeout):
        reader, writer = await _open_stream_connection(cot_url, config)
    eud_register_grace_s, post_send_hold_s = _stream_delay_config(cfg)
    try:
        if negotiate:
            await _negotiate_v1(reader, writer)
        for idx, frame in enumerate(frames):
            writer.write(frame)
            await writer.drain()
            if idx == 0 and len(frames) > 1 and eud_register_grace_s > 0:
                await asyncio.sleep(eud_register_grace_s)
        if post_send_hold_s > 0:
            await asyncio.sleep(post_send_hold_s)
    finally:
        writer.close()
        with contextlib.suppress(Exception):
            async with asyncio.timeout(2):
                await writer.wait_closed()


_DEFAULT_ENROLL_PORT = 8446
# Marti REST endpoints for soft-cert enrollment.
_TLS_CONFIG_PATH = "/Marti/api/tls/config"
_SIGN_CLIENT_V2_PATH = "/Marti/api/tls/signClient/v2"
_SIGN_CLIENT_PATH = "/Marti/api/tls/signClient"

# Mapping from TAK config nameEntry names to x509 OID short names. The CSR
# subject must carry these in addition to CN, or TAK Server rejects the CSR
# ("CSR validation failed!" → HTTP 500). Confirmed against the live server.
_NAME_ENTRY_OIDS = {
    "O": "ORGANIZATION_NAME",
    "OU": "ORGANIZATIONAL_UNIT_NAME",
    "C": "COUNTRY_NAME",
    "ST": "STATE_OR_PROVINCE_NAME",
    "L": "LOCALITY_NAME",
    "CN": "COMMON_NAME",
}


def _parse_name_entries(config_xml: bytes) -> list[tuple[str, str]]:
    """Extract ``(name, value)`` pairs from a ``/Marti/api/tls/config`` body.

    The connector returns ``<certificateConfig><nameEntries><nameEntry
    name="O" value="none"/>...``. These must be folded into the CSR subject.
    Returns an empty list if the body isn't parseable (we still send CN).
    """
    entries: list[tuple[str, str]] = []
    with contextlib.suppress(ET.ParseError, DefusedXmlException):
        # defusedxml hardens against XXE/billion-laughs — the connector reply is
        # network input even though the connection is auth'd + CA-verified.
        root = DET.fromstring(config_xml)
        # The body uses a default namespace (xmlns="...marti/xml/config"), so
        # match on the local tag name (strip any "{ns}" prefix) rather than a
        # literal "nameEntry" which would miss every namespaced element.
        for entry in root.iter():
            if entry.tag.rsplit("}", 1)[-1] != "nameEntry":
                continue
            name = entry.get("name")
            value = entry.get("value")
            if name and value is not None:
                entries.append((name, value))
    return entries


def _resolve_enroll_url(cfg: dict[str, Any]) -> str:
    """Resolve the cert-enrollment connector base URL.

    Explicit ``enroll_url`` wins. Otherwise derive ``https://<host>:<port>``
    from ``host`` (or the host embedded in ``cot_url``) and ``enroll_port``
    (default 8446 — the TAK Server cert-enrollment connector).
    """
    explicit = cfg.get("enroll_url")
    if explicit:
        return str(explicit).rstrip("/")

    host = cfg.get("host")
    if not host:
        cot_url = cfg.get("cot_url")
        if cot_url:
            host = urlsplit(str(cot_url)).hostname
    if not host:
        msg = "tak_server enrollment requires `enroll_url`, or `host`/`cot_url` to derive it from"
        raise ValueError(msg)

    port = int(cfg.get("enroll_port", _DEFAULT_ENROLL_PORT))
    return f"https://{host}:{port}"


def _build_csr(
    username: str,
    name_entries: list[tuple[str, str]] | None = None,
) -> tuple[bytes, bytes]:
    """Generate an RSA-2048 keypair and a PKCS#10 CSR with subject CN=username.

    Returns ``(csr_pem, key_pem)``. Mirrors what ATAK does during soft-cert
    enrollment: the server signs this CSR and hands back the client cert.

    ``name_entries`` are the ``(name, value)`` pairs from the connector's
    ``/Marti/api/tls/config`` (O/OU/C/...). They are folded into the CSR
    subject in addition to CN — the real TAK Server rejects a CN-only subject
    ("CSR validation failed!"). Any CN entry from the config is ignored in
    favour of the username.
    """
    from cryptography import x509  # noqa: PLC0415
    from cryptography.hazmat.primitives import hashes, serialization  # noqa: PLC0415
    from cryptography.hazmat.primitives.asymmetric import rsa  # noqa: PLC0415
    from cryptography.x509.oid import NameOID  # noqa: PLC0415

    attrs: list[x509.NameAttribute[str]] = [
        x509.NameAttribute(NameOID.COMMON_NAME, username),
    ]
    for name, value in name_entries or []:
        oid_attr = _NAME_ENTRY_OIDS.get(name.upper())
        if oid_attr is None or oid_attr == "COMMON_NAME":
            continue  # unknown RDN or a config CN (we use the username for CN)
        attrs.append(x509.NameAttribute(getattr(NameOID, oid_attr), value))

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name(attrs))
        .sign(key, hashes.SHA256())
    )
    csr_pem = csr.public_bytes(serialization.Encoding.PEM)
    key_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return csr_pem, key_pem


def _certs_from_json(body: bytes) -> list[bytes]:
    """Pull DER certs out of a signClient/v2 JSON response, leaf first.

    The modern connector returns ``{"signedCert": "<base64-DER>", "ca0":
    "<base64-DER>", "ca1": ...}`` — the leaf in ``signedCert``, the chain in
    ``ca0``, ``ca1`` ... Returns the DER blobs (leaf first) or ``[]`` if the
    body isn't this JSON shape.
    """
    import base64  # noqa: PLC0415
    import json  # noqa: PLC0415

    try:
        doc = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return []
    if not isinstance(doc, dict):
        return []

    ordered: list[str] = []
    leaf = doc.get("signedCert")
    if isinstance(leaf, str) and leaf:
        ordered.append(leaf)
    # ca0, ca1, ... in numeric order so the chain stays leaf→root.
    ca_keys = sorted(
        (k for k in doc if k.startswith("ca") and k[2:].isdigit()),
        key=lambda k: int(k[2:]),
    )
    ordered.extend(str(doc[k]) for k in ca_keys if isinstance(doc[k], str) and doc[k])
    out: list[bytes] = []
    for b64 in ordered:
        with contextlib.suppress(ValueError):
            out.append(base64.b64decode(b64))
    return out


def _extract_certs_pem(body: bytes) -> bytes:
    """Normalize a signClient response into a PEM cert (leaf + any chain).

    TAK Server may return:
      * a JSON envelope ``{"signedCert": "<b64-DER>", "ca0": "<b64-DER>", ...}``
        (the modern ``signClient/v2`` form),
      * a bare PEM cert or PEM chain,
      * a PKCS7/p7b bundle (DER or PEM).
    We return concatenated PEM certificate(s) suitable for ``load_cert_chain``;
    the leaf comes first.
    """
    from cryptography import x509  # noqa: PLC0415
    from cryptography.hazmat.primitives import serialization  # noqa: PLC0415
    from cryptography.hazmat.primitives.serialization import pkcs7  # noqa: PLC0415

    text = body.lstrip()
    certs: list[x509.Certificate] = []

    # JSON envelope (signClient/v2): {"signedCert": "<b64-DER>", "ca0": ...}
    if text.startswith(b"{"):
        certs = [x509.load_der_x509_certificate(d) for d in _certs_from_json(body)]
        if certs:
            return b"".join(c.public_bytes(serialization.Encoding.PEM) for c in certs)

    # Already PEM certificate(s) — pass through unchanged.
    if text.startswith(b"-----BEGIN CERTIFICATE-----"):
        return body

    # PKCS7, PEM-armored ("-----BEGIN PKCS7-----") or DER.
    if text.startswith(b"-----BEGIN PKCS7-----") or text.startswith(b"-----BEGIN PKCS #7"):
        certs = list(pkcs7.load_pem_pkcs7_certificates(body))
    else:
        with contextlib.suppress(ValueError):
            certs = list(pkcs7.load_der_pkcs7_certificates(body))
    if not certs:
        msg = "tak_server enrollment: signClient response is not a recognized cert/PKCS7"
        raise RuntimeError(msg)
    return b"".join(c.public_bytes(serialization.Encoding.PEM) for c in certs)


def _enroll_client_cert(cfg: dict[str, Any]) -> tuple[Path, Path]:
    """Run the TAK soft-cert enrollment flow and return ``(cert_path, key_path)``.

    1. GET ``/Marti/api/tls/config`` (Basic auth) — confirm the connector and
       read the CA name config (O/OU/C nameEntries).
    2. Generate a keypair + CSR whose subject is CN=username plus those
       nameEntries (a CN-only subject is rejected by the real server).
    3. POST the CSR to ``/Marti/api/tls/signClient/v2`` (fallback
       ``/signClient``) and capture the issued client cert. The response may be
       a JSON envelope (``signedCert``/``ca*`` base64-DER), bare PEM, or PKCS7.

    The cert + key are written to a private temp directory (0700/0600) and the
    paths returned for the pytak mTLS stream to consume.
    """
    username = str(cfg["username"])
    password = str(cfg["password"])
    base = _resolve_enroll_url(cfg)
    timeout = float(cfg.get("timeout_seconds", 10))

    verify_server = bool(cfg.get("verify_server", True))
    ca_path = cfg.get("ca_cert_pem_path")
    # The connector is server-auth TLS only (no client cert). Verify its cert
    # against the provided CA file when given, else system CAs — unless the
    # operator opts out via verify_server=false.
    verify: bool | ssl.SSLContext
    if not verify_server:
        verify = False
    elif ca_path:
        verify = ssl.create_default_context(cafile=str(ca_path))
    else:
        verify = True

    auth = (username, password)
    with httpx.Client(verify=verify, timeout=timeout, auth=auth) as client:
        # 1) CA config — proves the connector is reachable + credentials work,
        #    and yields the nameEntries the CSR subject must carry (O/OU/C/...).
        cfg_resp = client.get(f"{base}{_TLS_CONFIG_PATH}")
        cfg_resp.raise_for_status()
        name_entries = _parse_name_entries(cfg_resp.content)

        # 2) keypair + CSR (CN=username plus the advertised nameEntries)
        csr_pem, key_pem = _build_csr(username, name_entries)

        # 3) sign — try the versioned endpoint first, fall back to the legacy one.
        client_uid = str(cfg.get("client_uid", username))
        version = str(cfg.get("client_uid_version", "3"))
        params = {"clientUid": client_uid, "version": version}
        headers = {"Content-Type": "application/octet-stream"}
        sign_resp = client.post(
            f"{base}{_SIGN_CLIENT_V2_PATH}",
            params=params,
            content=csr_pem,
            headers=headers,
        )
        if sign_resp.status_code == httpx.codes.NOT_FOUND:
            sign_resp = client.post(
                f"{base}{_SIGN_CLIENT_PATH}",
                params=params,
                content=csr_pem,
                headers=headers,
            )
        sign_resp.raise_for_status()
        cert_pem = _extract_certs_pem(sign_resp.content)

    workdir = Path(tempfile.mkdtemp(prefix="tw-tak-enroll-"))
    cert_path = workdir / "client.pem"
    key_path = workdir / "client.key"
    cert_path.write_bytes(cert_pem)
    key_path.write_bytes(key_pem)
    os.chmod(cert_path, 0o600)
    os.chmod(key_path, 0o600)
    return cert_path, key_path


class TakServerPublisher:
    name = "tak_server"

    def publish(self, *, target: Any, adapter_config: dict[str, Any]) -> None:
        # Soft-cert enrollment: username + password → fetch a client cert from
        # the enrollment connector (8446), then stream with it.
        if adapter_config.get("username") and adapter_config.get("password"):
            self._publish_via_enrollment(target=target, adapter_config=adapter_config)
        elif self._is_quic(adapter_config):
            self._publish_via_quic(target=target, adapter_config=adapter_config)
        elif adapter_config.get("cot_url") or adapter_config.get("transport"):
            self._publish_via_pytak(target=target, adapter_config=adapter_config)
        else:
            self._publish_via_mtls(target=target, adapter_config=adapter_config)

    # ── soft-cert enrollment (username/password → client cert → stream) ────
    def _publish_via_enrollment(self, *, target: Any, adapter_config: dict[str, Any]) -> None:
        cert_path, key_path = _enroll_client_cert(adapter_config)
        # The issued cert is for the mTLS stream on 8089; force a tls:// stream
        # so the pytak path picks up the client cert.
        cfg = dict(adapter_config)
        cfg["client_cert_pem_path"] = str(cert_path)
        cfg["client_key_pem_path"] = str(key_path)
        cfg.setdefault("transport", "tls")
        if not cfg.get("cot_url") and not cfg.get("host"):
            base_host = urlsplit(_resolve_enroll_url(adapter_config)).hostname
            if base_host:
                cfg["host"] = base_host
                cfg.setdefault("port", 8089)
        self._publish_via_pytak(target=target, adapter_config=cfg)

    @staticmethod
    def _is_quic(cfg: dict[str, Any]) -> bool:
        return str(cfg.get("transport", "")).lower() == "quic" or str(
            cfg.get("cot_url", "")
        ).lower().startswith("quic://")

    # ── QUIC (TAK Protocol v1 over a bidi QUIC stream) ─────────────────────
    def _publish_via_quic(self, *, target: Any, adapter_config: dict[str, Any]) -> None:
        host, port = self._resolve_quic_host_port(adapter_config)
        cert_path = adapter_config.get("client_cert_pem_path")
        key_path = adapter_config.get("client_key_pem_path")
        if not cert_path or not key_path:
            msg = "tak_server QUIC transport requires client_cert_pem_path + client_key_pem_path"
            raise ValueError(msg)
        public_url = adapter_config.get("public_url")
        board_id = adapter_config.get("board_id")
        target_bytes = target_to_cot_xml(
            target,
            public_url=str(public_url) if public_url else None,
            board_id=str(board_id) if board_id else None,
        )
        self_sa = _self_sa_xml(
            eud_uid=str(adapter_config.get("eud_uid", "target-workspace-eud")),
            callsign=str(adapter_config.get("eud_callsign", "target-workspace")),
            lat=float(getattr(target, "lat", 0.0) or 0.0),
            lon=float(getattr(target, "lon", 0.0) or 0.0),
        )
        frames = [_to_tak_v1(self_sa), _to_tak_v1(target_bytes)]
        ca_path = adapter_config.get("ca_cert_pem_path")
        self._publish_quic(
            host=host,
            port=port,
            frames=frames,
            cert_path=str(cert_path),
            key_path=str(key_path),
            ca_path=str(ca_path) if ca_path else None,
            verify_hostname=bool(adapter_config.get("verify_hostname", True)),
            timeout=float(adapter_config.get("timeout_seconds", 10)),
            alpn=TAK_QUIC_ALPN,
        )

    @staticmethod
    def _resolve_quic_host_port(cfg: dict[str, Any]) -> tuple[str, int]:
        url = str(cfg.get("cot_url", ""))
        if url.lower().startswith("quic://"):
            rest = url[len("quic://") :]
            host, _, port_s = rest.partition(":")
            return host, int(port_s) if port_s else TAK_QUIC_DEFAULT_PORT
        host_cfg = cfg.get("host")
        if not host_cfg:
            msg = "tak_server QUIC transport requires `cot_url` (quic://...) or `host`"
            raise ValueError(msg)
        return str(host_cfg), int(cfg.get("port", TAK_QUIC_DEFAULT_PORT))

    def _publish_quic(
        self,
        *,
        host: str,
        port: int,
        frames: list[bytes],
        cert_path: str,
        key_path: str,
        ca_path: str | None,
        verify_hostname: bool,
        timeout: float,
        alpn: str,
    ) -> None:
        """Open a QUIC mTLS connection, write the frames on one bidi stream,
        flush, and close. Synchronous wrapper bounded by ``timeout`` so a hung
        handshake never blocks the workflow engine."""

        async def _bounded() -> None:
            async with asyncio.timeout(timeout):
                await self._publish_quic_async(
                    host=host,
                    port=port,
                    frames=frames,
                    cert_path=cert_path,
                    key_path=key_path,
                    ca_path=ca_path,
                    verify_hostname=verify_hostname,
                    alpn=alpn,
                )

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_bounded())
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

    async def _publish_quic_async(
        self,
        *,
        host: str,
        port: int,
        frames: list[bytes],
        cert_path: str,
        key_path: str,
        ca_path: str | None,
        verify_hostname: bool,
        alpn: str,
    ) -> None:
        from aioquic.asyncio.client import connect  # noqa: PLC0415 — only QUIC needs aioquic
        from aioquic.quic.configuration import QuicConfiguration  # noqa: PLC0415

        config = QuicConfiguration(is_client=True, alpn_protocols=[alpn])
        if ca_path:
            config.load_verify_locations(cafile=ca_path)
        if not verify_hostname:
            config.verify_mode = ssl.CERT_NONE
        config.load_cert_chain(certfile=cert_path, keyfile=key_path)

        async with connect(host, port, configuration=config, wait_connected=True) as protocol:
            # Single client-initiated bidi stream. Like TLS streaming, the QUIC
            # input starts in XML (v0): negotiate to v1 on the stream first, then
            # send the STREAM frames (self-SA first so the EUD registers).
            reader, writer = await protocol.create_stream(is_unidirectional=False)
            writer.write(_negotiation_request_xml())
            protocol.transmit()
            with contextlib.suppress(Exception):
                async with asyncio.timeout(_NEGOTIATION_RESPONSE_TIMEOUT_S):
                    buf = b""
                    while b"takp-r" not in buf and b"TakResponse" not in buf:
                        chunk = await reader.read(4096)
                        if not chunk:
                            break
                        buf += chunk
            for frame in frames:
                writer.write(frame)
            writer.write_eof()
            await writer.drain()
            writer.close()
            protocol.transmit()
            protocol.close()
            await protocol.wait_closed()
            await asyncio.sleep(0)

    # ── pytak stream (self-SA → target): the real-TAK-Server path ──────────
    def _publish_via_pytak(self, *, target: Any, adapter_config: dict[str, Any]) -> None:
        cot_url = self._resolve_cot_url(adapter_config)
        public_url = adapter_config.get("public_url")
        board_id = adapter_config.get("board_id")
        target_bytes = target_to_cot_xml(
            target,
            public_url=str(public_url) if public_url else None,
            board_id=str(board_id) if board_id else None,
        )
        frames: list[bytes] = []
        eud_uid = adapter_config.get("eud_uid")
        if eud_uid:
            frames.append(
                _self_sa_xml(
                    eud_uid=str(eud_uid),
                    callsign=str(adapter_config.get("eud_callsign", "target-workspace")),
                    lat=float(getattr(target, "lat", 0.0) or 0.0),
                    lon=float(getattr(target, "lon", 0.0) or 0.0),
                ),
            )
        frames.append(target_bytes)
        protobuf = str(adapter_config.get("protocol", "xml")).lower() in _PROTOBUF_MODES
        if protobuf:
            frames = [_to_tak_v1(f) for f in frames]
        asyncio.run(_stream(cot_url, adapter_config, frames, negotiate=protobuf))

    @staticmethod
    def _resolve_cot_url(cfg: dict[str, Any]) -> str:
        url = cfg.get("cot_url")
        if url:
            return str(url)
        host = cfg.get("host")
        if not host:
            msg = "tak_server publisher requires `cot_url` or `host` in adapter_config"
            raise ValueError(msg)
        transport = str(cfg.get("transport", "tls"))
        port = int(cfg.get("port", 8089))
        return f"{transport}://{host}:{port}"

    # ── legacy stdlib mTLS (one CoT over a client-cert TLS socket) ─────────
    def _publish_via_mtls(self, *, target: Any, adapter_config: dict[str, Any]) -> None:
        host = str(adapter_config.get("host", ""))
        port = int(adapter_config.get("port", 8089))
        cert_path = adapter_config.get("client_cert_pem_path")
        key_path = adapter_config.get("client_key_pem_path")
        ca_path = adapter_config.get("ca_cert_pem_path")
        verify_hostname = bool(adapter_config.get("verify_hostname", True))
        timeout = float(adapter_config.get("timeout_seconds", 5))
        public_url = adapter_config.get("public_url")
        board_id = adapter_config.get("board_id")

        if not host:
            msg = "tak_server publisher requires `host` in adapter_config"
            raise ValueError(msg)
        if not cert_path or not key_path:
            msg = (
                "tak_server publisher requires `client_cert_pem_path` and "
                "`client_key_pem_path` for mTLS client authentication"
            )
            raise ValueError(msg)

        cert_checks: list[tuple[str, Any]] = [("client_cert", cert_path), ("client_key", key_path)]
        if ca_path:
            cert_checks.append(("ca_cert", ca_path))
        for label, p in cert_checks:
            if not Path(str(p)).is_file():
                msg = f"tak_server: {label} file not found: {p}"
                raise FileNotFoundError(msg)

        ctx = ssl.create_default_context(
            purpose=ssl.Purpose.SERVER_AUTH,
            cafile=str(ca_path) if ca_path else None,
        )
        ctx.check_hostname = verify_hostname
        ctx.verify_mode = ssl.CERT_REQUIRED
        ctx.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))

        payload = target_to_cot_xml(
            target,
            public_url=str(public_url) if public_url else None,
            board_id=str(board_id) if board_id else None,
        )

        with (
            socket.create_connection((host, port), timeout=timeout) as raw,
            ctx.wrap_socket(raw, server_hostname=host) as tls,
        ):
            tls.sendall(payload + b"\n")


register_publisher(TakServerPublisher.name, TakServerPublisher)
