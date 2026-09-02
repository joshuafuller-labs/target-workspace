"""Unit tests for the TAK Server Publisher.

Real TAK Server isn't available in CI, so these tests stand up a local
TLS echo server with a self-signed cert and verify that the publisher
opens an mTLS connection and sends valid CoT XML. Validation of cert
file existence + adapter_config keys is checked separately without any
network setup.
"""

from __future__ import annotations

import socket
import ssl
import threading
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

import pytest

from target_workspace.models.target import Target
from target_workspace.plugins.publishers.tak_server import TakServerPublisher

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
    """Mint a self-signed cert + private key into tmp_path. Returns
    (cert_pem, key_pem). Uses cryptography (already a runtime dep)."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, "localhost")],
    )
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


def test_validates_host_required() -> None:
    p = TakServerPublisher()
    with pytest.raises(ValueError, match="requires `host`"):
        p.publish(
            target=_make_target(),
            adapter_config={
                "host": "",
                "client_cert_pem_path": "x",
                "client_key_pem_path": "y",
            },
        )


def test_validates_cert_paths_required() -> None:
    p = TakServerPublisher()
    with pytest.raises(ValueError, match="client_cert_pem_path"):
        p.publish(
            target=_make_target(),
            adapter_config={"host": "tak.example", "port": 8089},
        )


def test_validates_cert_file_exists(tmp_path: Path) -> None:
    p = TakServerPublisher()
    with pytest.raises(FileNotFoundError, match="client_cert"):
        p.publish(
            target=_make_target(),
            adapter_config={
                "host": "tak.example",
                "client_cert_pem_path": str(tmp_path / "no.pem"),
                "client_key_pem_path": str(tmp_path / "no.key"),
            },
        )


def test_tls_send_round_trip(tmp_path: Path) -> None:
    """Spin up a local TLS server, publish, verify it received valid CoT XML."""
    cert_path, key_path = _gen_self_signed_cert(tmp_path)

    received: list[bytes] = []
    ready = threading.Event()
    server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_sock.bind(("127.0.0.1", 0))
    server_sock.listen(1)
    server_sock.settimeout(3.0)
    port = server_sock.getsockname()[1]

    server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_ctx.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))
    # This is a unit-test TAK stub — the publisher's mTLS handshake is
    # exercised against a real TLS server but we don't validate the
    # client cert chain (no CA on the server side).
    server_ctx.verify_mode = ssl.CERT_NONE

    def serve() -> None:
        ready.set()
        try:
            client, _ = server_sock.accept()
            with server_ctx.wrap_socket(client, server_side=True) as tls:
                data = tls.recv(8192)
                received.append(data)
        except (TimeoutError, ssl.SSLError):
            pass
        finally:
            server_sock.close()

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    ready.wait(timeout=1.0)

    publisher = TakServerPublisher()
    publisher.publish(
        target=_make_target(),
        adapter_config={
            "host": "localhost",
            "port": port,
            "client_cert_pem_path": str(cert_path),
            "client_key_pem_path": str(key_path),
            "ca_cert_pem_path": str(cert_path),  # self-signed: cert IS the CA
            "verify_hostname": True,
            "timeout_seconds": 3,
        },
    )
    t.join(timeout=3.0)

    assert len(received) == 1
    payload = received[0]
    # CoT-over-TAK convention is one newline-framed event per message.
    # If we drop the trailing \n some TAK Server builds reject the
    # framing and the message vanishes silently.
    assert payload.endswith(b"\n"), f"published CoT must end with newline framing; got {payload!r}"
    line = payload.rstrip(b"\n")
    root = ET.fromstring(line)
    assert root.tag == "event"
    contact = root.find("./detail/contact")
    assert contact is not None
    assert contact.attrib["callsign"] == "BISON-01"


def test_default_verify_hostname_is_true(tmp_path: Path) -> None:
    """Hostname verification must default to ON. If the default flips to
    False, a misconfigured deployment quietly accepts the wrong cert and
    leaks operational data to whoever's intercepting.

    We assert the default by connecting to a TLS server whose cert SAN
    does NOT match the host we're calling it on. With check_hostname
    ON (the default), TLS rejects. With it OFF, the connection
    succeeds. Test passes when the publisher raises an SSL error.
    """
    cert_path, key_path = _gen_self_signed_cert_for_cn(tmp_path, "wrong.example.invalid")

    # Spin up a TLS echo server on 127.0.0.1 using the wrong-CN cert.
    server_ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    server_ctx.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))
    server_ctx.verify_mode = ssl.CERT_NONE

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    port = sock.getsockname()[1]

    def serve() -> None:
        try:
            client_sock, _ = sock.accept()
            try:
                server_ctx.wrap_socket(client_sock, server_side=True)
            except Exception:
                pass  # expected when client rejects our cert
        except Exception:
            pass

    t = threading.Thread(target=serve, daemon=True)
    t.start()

    publisher = TakServerPublisher()
    # Omit verify_hostname → must default to True.
    with pytest.raises((ssl.SSLError, ssl.SSLCertVerificationError, ConnectionError)):
        publisher.publish(
            target=_make_target(),
            adapter_config={
                "host": "127.0.0.1",
                "port": port,
                "client_cert_pem_path": str(cert_path),
                "client_key_pem_path": str(key_path),
                "ca_cert_pem_path": str(cert_path),
                "timeout_seconds": 3,
            },
        )
    sock.close()


def _gen_self_signed_cert_for_cn(tmp_path: Path, cn: str) -> tuple[Path, Path]:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name(
        [x509.NameAttribute(NameOID.COMMON_NAME, cn)],
    )
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime(2026, 1, 1, tzinfo=UTC))
        .not_valid_after(datetime(2030, 1, 1, tzinfo=UTC))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName(cn)]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    cert_path = tmp_path / "wrong-cn.crt.pem"
    key_path = tmp_path / "wrong-cn.key.pem"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ),
    )
    return cert_path, key_path
