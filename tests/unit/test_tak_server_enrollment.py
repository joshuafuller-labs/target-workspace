"""TDD: TAK Server username/password certificate enrollment ("soft cert").

What ATAK does when a user types a username + password instead of importing
a client cert: it talks to the TAK Server cert-enrollment connector (default
port 8446, server-auth TLS only — NO client cert) over HTTP Basic auth, asks
for the CA config, submits a PKCS#10 CSR, and gets back a signed client
certificate. It then uses that cert to stream CoT to 8089.

Contract pinned here, exercised against LOCAL mocks only:

  1. The publisher GETs ``/Marti/api/tls/config`` with an
     ``Authorization: Basic`` header.
  2. It POSTs a PKCS#10 CSR (PEM) to ``/Marti/api/tls/signClient/v2`` (also
     Basic auth) — the body parses as a real CSR whose subject CN is the
     username.
  3. With the issued cert it connects to the CoT stream endpoint and sends
     the self-SA followed by the target over one connection.

No real server is contacted: the enrollment connector is a stdlib
``http.server`` + ``ssl`` HTTPS server with a self-signed cert generated
in-test, and the CoT stream is captured at the TCP layer (the
``_CaptureEndpoint`` pattern from test_tak_server_selfsa.py).
"""

from __future__ import annotations

import base64
import ipaddress
import json
import socket
import ssl
import threading
import xml.etree.ElementTree as ET
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.x509.oid import NameOID

from target_workspace.models.target import Target
from target_workspace.plugins.publishers.tak_server import (
    TakServerPublisher,
    _build_csr,
    _extract_certs_pem,
    _resolve_enroll_url,
)

if TYPE_CHECKING:
    from cryptography.hazmat.primitives.asymmetric.rsa import (
        RSAPrivateKey,
        RSAPublicKey,
    )

pytestmark = [pytest.mark.fast]

_USERNAME = "user"
_PASSWORD = "pass"  # pragma: allowlist secret


# ── self-SA + target capture (TCP layer) ──────────────────────────────────
class _CaptureEndpoint:
    """Threaded TCP server standing in for the TAK CoT stream port; captures
    the full byte stream the publisher sends over one connection."""

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
        finally:
            self.done.set()

    def wait(self, timeout: float = 2.0) -> bool:
        return self.done.wait(timeout)

    def stop(self) -> None:
        self._sock.close()
        self._thread.join(timeout=1)


# ── mock TAK cert-enrollment HTTPS connector ───────────────────────────────
def _make_ca() -> tuple[RSAPrivateKey, x509.Certificate]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "TAK-CA")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime(2026, 1, 1, tzinfo=UTC))
        .not_valid_after(datetime(2030, 1, 1, tzinfo=UTC))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    return key, cert


def _server_tls_cert(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Self-signed server cert (CN=localhost) for the HTTPS connector.
    Returns (server_cert_pem, server_key_pem, ca_pem) — for a self-signed
    cert the cert IS its own CA, so ca_pem == server_cert_pem content."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime(2026, 1, 1, tzinfo=UTC))
        .not_valid_after(datetime(2030, 1, 1, tzinfo=UTC))
        .add_extension(
            x509.SubjectAlternativeName(
                [x509.DNSName("localhost"), x509.IPAddress(_ip("127.0.0.1"))],
            ),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    cert_pem = tmp_path / "server.pem"
    key_pem = tmp_path / "server.key"
    ca_pem = tmp_path / "ca.pem"
    cert_bytes = cert.public_bytes(serialization.Encoding.PEM)
    cert_pem.write_bytes(cert_bytes)
    ca_pem.write_bytes(cert_bytes)
    key_pem.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
    )
    return cert_pem, key_pem, ca_pem


def _ip(addr: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    return ipaddress.ip_address(addr)


# The name entries the mock config connector advertises. The real TAK Server
# rejects a CN-only CSR ("CSR validation failed!" → HTTP 500), so these MUST be
# folded into the CSR subject by the publisher.
_CONFIG_NAME_ENTRIES: list[tuple[str, str]] = [
    ("O", "none"),
    ("OU", "none"),
    ("C", "US"),
]


def _sign_csr(csr_pem: bytes, ca_key: RSAPrivateKey, ca_cert: x509.Certificate) -> bytes:
    csr = x509.load_pem_x509_csr(csr_pem)
    pub: RSAPublicKey = csr.public_key()  # type: ignore[assignment]
    cert = (
        x509.CertificateBuilder()
        .subject_name(csr.subject)
        .issuer_name(ca_cert.subject)
        .public_key(pub)
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(tz=UTC) - timedelta(minutes=1))
        .not_valid_after(datetime.now(tz=UTC) + timedelta(days=365))
        .sign(ca_key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM)


_NAME_OID = {
    "O": NameOID.ORGANIZATION_NAME,
    "OU": NameOID.ORGANIZATIONAL_UNIT_NAME,
    "C": NameOID.COUNTRY_NAME,
}


def _csr_subject_has_entries(csr: x509.CertificateSigningRequest) -> bool:
    """Replicate the real server's subject validation: the CSR subject must
    carry every advertised nameEntry (O/OU/C), not just CN."""
    for name, value in _CONFIG_NAME_ENTRIES:
        oid = _NAME_OID[name]
        attrs = csr.subject.get_attributes_for_oid(oid)
        if not attrs or attrs[0].value != value:
            return False
    return True


class _EnrollServer:
    """Mock TAK cert-enrollment HTTPS connector. Records every request
    (path, auth header, body) and signs CSRs with an in-test CA."""

    def __init__(self, tmp_path: Path) -> None:
        self.ca_key, self.ca_cert = _make_ca()
        cert_pem, key_pem, self.ca_pem = _server_tls_cert(tmp_path)
        self.requests: list[dict[str, object]] = []
        captured = self.requests
        ca_key, ca_cert = self.ca_key, self.ca_cert

        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args: object) -> None:  # silence
                return

            def _record(self, body: bytes) -> None:
                captured.append(
                    {
                        "method": self.command,
                        "path": self.path,
                        "auth": self.headers.get("Authorization"),
                        "body": body,
                    },
                )

            def _reply(self, code: int, body: bytes, content_type: str) -> None:
                self.send_response(code)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self) -> None:
                self._record(b"")
                if self.path.startswith("/Marti/api/tls/config"):
                    entries = b"".join(
                        f'<nameEntry name="{n}" value="{v}"/>'.encode()
                        for n, v in _CONFIG_NAME_ENTRIES
                    )
                    # Match the real connector: a DEFAULT namespace + ns2 prefix.
                    # A namespace-naive parser misses every <nameEntry> here.
                    xml = (
                        b"<?xml version='1.0' encoding='UTF-8' standalone='yes'?>"
                        b'<ns2:certificateConfig xmlns="http://bbn.com/marti/xml/config"'
                        b' xmlns:ns2="com.bbn.marti.config"><nameEntries>'
                        + entries
                        + b"</nameEntries></ns2:certificateConfig>"
                    )
                    self._reply(200, xml, "application/xml")
                else:
                    self._reply(404, b"", "text/plain")

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                body = self.rfile.read(length)
                self._record(body)
                if "/Marti/api/tls/signClient" not in self.path:
                    self._reply(404, b"", "text/plain")
                    return
                csr = x509.load_pem_x509_csr(body)
                # Mirror the live server: a CN-only CSR fails subject validation
                # ("CSR validation failed!") and the endpoint returns HTTP 500.
                if not _csr_subject_has_entries(csr):
                    self._reply(500, b"signClient returned null", "text/plain")
                    return
                signed_pem = _sign_csr(body, ca_key, ca_cert)
                leaf_der = x509.load_pem_x509_certificate(signed_pem).public_bytes(
                    serialization.Encoding.DER,
                )
                ca_der = ca_cert.public_bytes(serialization.Encoding.DER)
                payload = json.dumps(
                    {
                        "signedCert": base64.b64encode(leaf_der).decode("ascii"),
                        "ca0": base64.b64encode(ca_der).decode("ascii"),
                    },
                ).encode()
                self._reply(200, payload, "application/json")

        self._httpd = HTTPServer(("127.0.0.1", 0), _Handler)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(certfile=str(cert_pem), keyfile=str(key_pem))
        self._httpd.socket = ctx.wrap_socket(self._httpd.socket, server_side=True)
        self.port: int = self._httpd.server_address[1]
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
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


def test_username_password_enrollment_then_stream(tmp_path: Path) -> None:
    """Full soft-cert flow: enroll over 8446-style HTTPS connector, then
    stream the self-SA + target to the CoT endpoint with the issued cert."""
    enroll = _EnrollServer(tmp_path)
    enroll.start()
    stream = _CaptureEndpoint()
    stream.start()

    try:
        TakServerPublisher().publish(
            target=_target(),
            adapter_config={
                # CoT stream destination (issued cert used here):
                "cot_url": f"tcp://127.0.0.1:{stream.port}",
                "eud_uid": "TW-PUBLISHER-EUD",
                "eud_callsign": "TARGET-WORKBENCH",
                # Soft-cert enrollment (triggers when username+password set):
                "username": _USERNAME,
                "password": _PASSWORD,
                "enroll_url": f"https://127.0.0.1:{enroll.port}",
                "ca_cert_pem_path": str(enroll.ca_pem),
                "eud_register_grace_seconds": 0,
                "post_send_hold_seconds": 0,
            },
        )
        assert stream.wait(), "capture endpoint did not finish reading enrolled stream"
    finally:
        stream.stop()
        enroll.stop()

    # (a) hit /Marti/api/tls/config AND /Marti/api/tls/signClient* with Basic auth
    paths = [str(r["path"]) for r in enroll.requests]
    assert any(p.startswith("/Marti/api/tls/config") for p in paths), paths
    assert any("/Marti/api/tls/signClient" in p for p in paths), paths

    expected_auth = "Basic " + base64.b64encode(
        f"{_USERNAME}:{_PASSWORD}".encode(),
    ).decode("ascii")
    for r in enroll.requests:
        assert r["auth"] == expected_auth, f"missing/wrong Basic auth: {r['auth']!r}"

    # (b) the POST body is a real PKCS#10 CSR whose subject CN is the username
    # AND carries the nameEntries from /Marti/api/tls/config (O/OU/C). A CN-only
    # subject is rejected by the real server, so the publisher must fold them in.
    sign_req = next(r for r in enroll.requests if "/signClient" in str(r["path"]))
    csr_body = sign_req["body"]
    assert isinstance(csr_body, bytes)
    csr = x509.load_pem_x509_csr(csr_body)
    cn = csr.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
    assert cn == _USERNAME
    assert _csr_subject_has_entries(csr), (
        "CSR subject must include the config nameEntries (O/OU/C), not just CN; "
        f"got {csr.subject.rfc4514_string()}"
    )
    # signClient/v2 carried the version query param the live server requires.
    assert "version=" in str(sign_req["path"]), sign_req["path"]

    # (c) self-SA + target reached the CoT stream endpoint over one connection
    events = _events(stream.data)
    assert len(events) >= 2, f"expected self-SA + target; got: {stream.data[:300]!r}"
    self_sa, tgt = events[0], events[1]
    assert self_sa.attrib["uid"] == "TW-PUBLISHER-EUD"
    assert self_sa.attrib["type"].startswith("a-f-")
    assert tgt.attrib["type"] == "a-h-G-U-C-I"
    tcontact = tgt.find(".//contact")
    assert tcontact is not None
    assert tcontact.attrib.get("callsign") == "HOSTILE-ALPHA"


def test_enrollment_default_port_is_8446() -> None:
    """When only username+password (and host) are given — no explicit
    enroll_url / enroll_port — the connector default port is 8446."""
    url = _resolve_enroll_url(
        {"host": "example", "username": _USERNAME, "password": _PASSWORD},
    )
    assert url == "https://example:8446"

    url2 = _resolve_enroll_url(
        {
            "cot_url": "tcp://example:8088",
            "username": _USERNAME,
            "password": _PASSWORD,
            "enroll_port": 8443,
        },
    )
    assert url2 == "https://example:8443"


def test_extract_certs_pem_handles_pkcs7_chain() -> None:
    """TAK Server may return the signed cert as a PKCS7/p7b bundle. The
    publisher must extract the leaf (+ chain) into usable PEM."""
    ca_key, ca_cert = _make_ca()
    csr_pem, _key = _build_csr(_USERNAME)
    leaf_pem = _sign_csr(csr_pem, ca_key, ca_cert)
    leaf = x509.load_pem_x509_certificate(leaf_pem)

    # Build a DER PKCS7 bundle (leaf + CA), the p7b form TAK can return.
    der_p7 = pkcs7.serialize_certificates([leaf, ca_cert], serialization.Encoding.DER)
    out = _extract_certs_pem(der_p7)
    assert out.lstrip().startswith(b"-----BEGIN CERTIFICATE-----")
    parsed = x509.load_pem_x509_certificate(out)
    assert parsed.subject == leaf.subject

    # And a bare PEM cert passes straight through.
    assert _extract_certs_pem(leaf_pem) == leaf_pem


def test_extract_certs_pem_handles_signclient_v2_json() -> None:
    """The modern signClient/v2 connector returns JSON:
    {"signedCert": "<base64-DER>", "ca0": "<base64-DER>", ...}. The publisher
    must base64-decode the DER and emit a PEM leaf (+ chain), leaf first."""
    ca_key, ca_cert = _make_ca()
    csr_pem, _key = _build_csr(_USERNAME, _CONFIG_NAME_ENTRIES)
    leaf = x509.load_pem_x509_certificate(_sign_csr(csr_pem, ca_key, ca_cert))

    envelope = json.dumps(
        {
            "signedCert": base64.b64encode(
                leaf.public_bytes(serialization.Encoding.DER),
            ).decode("ascii"),
            "ca0": base64.b64encode(
                ca_cert.public_bytes(serialization.Encoding.DER),
            ).decode("ascii"),
        },
    ).encode()

    out = _extract_certs_pem(envelope)
    blocks = out.split(b"-----END CERTIFICATE-----")
    assert out.count(b"-----BEGIN CERTIFICATE-----") == 2  # leaf + ca0
    leaf_out = x509.load_pem_x509_certificate(
        blocks[0] + b"-----END CERTIFICATE-----\n",
    )
    assert leaf_out.subject == leaf.subject  # leaf comes first


def test_build_csr_folds_config_name_entries() -> None:
    """The CSR subject must carry the config nameEntries (O/OU/C), not just CN."""
    csr_pem, _key = _build_csr(_USERNAME, _CONFIG_NAME_ENTRIES)
    csr = x509.load_pem_x509_csr(csr_pem)
    assert csr.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value == _USERNAME
    assert _csr_subject_has_entries(csr)
    # Without the entries, the subject is CN-only (would be rejected upstream).
    cn_only = x509.load_pem_x509_csr(_build_csr(_USERNAME)[0])
    assert not _csr_subject_has_entries(cn_only)
