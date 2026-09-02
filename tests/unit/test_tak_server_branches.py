"""Branch + error-path coverage for the tak_server publisher.

Exercises the config resolvers, validation raises, and the enrollment
response parsers (JSON / PEM / PKCS7) that the transport/enrollment happy-path
tests don't reach — without any network.
"""

from __future__ import annotations

import base64
from datetime import UTC, datetime

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.x509.oid import NameOID

from target_workspace.models.target import Target
from target_workspace.plugins.publishers import tak_server as t

pytestmark = [pytest.mark.fast]


def _target() -> Target:
    return Target(
        name="T",
        cot_type="a-h-G",
        lat=1.0,
        lon=2.0,
        time=datetime(2026, 5, 16, tzinfo=UTC),
        confidence=0.5,
    )


def _self_signed() -> x509.Certificate:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "leaf")])
    return (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime(2026, 1, 1, tzinfo=UTC))
        .not_valid_after(datetime(2030, 1, 1, tzinfo=UTC))
        .sign(key, hashes.SHA256())
    )


# ── resolvers ──────────────────────────────────────────────────────────────
def test_resolve_quic_host_port_variants() -> None:
    r = t.TakServerPublisher._resolve_quic_host_port
    assert r({"cot_url": "quic://h.example:9000"}) == ("h.example", 9000)
    assert r({"cot_url": "quic://h.example"}) == ("h.example", t.TAK_QUIC_DEFAULT_PORT)
    assert r({"host": "h2", "port": 8090}) == ("h2", 8090)
    with pytest.raises(ValueError, match="cot_url"):
        r({})


def test_resolve_cot_url_variants() -> None:
    r = t.TakServerPublisher._resolve_cot_url
    assert r({"cot_url": "tls://h:8089"}) == "tls://h:8089"
    assert r({"host": "h", "transport": "tcp", "port": 8087}) == "tcp://h:8087"
    with pytest.raises(ValueError, match="cot_url"):
        r({})


def test_resolve_enroll_url_variants() -> None:
    assert t._resolve_enroll_url({"enroll_url": "https://e:8446/"}) == "https://e:8446"
    assert t._resolve_enroll_url({"host": "h"}) == "https://h:8446"
    assert t._resolve_enroll_url({"host": "h", "enroll_port": 9446}) == "https://h:9446"
    assert t._resolve_enroll_url({"cot_url": "tls://h3:8089"}) == "https://h3:8446"
    with pytest.raises(ValueError, match="enroll_url"):
        t._resolve_enroll_url({})


def test_stream_delay_config_defaults_and_explicit_zero() -> None:
    assert t._stream_delay_config({}) == (t._EUD_REGISTER_GRACE_S, t._POST_SEND_HOLD_S)
    assert t._stream_delay_config(
        {
            "eud_register_grace_seconds": 0,
            "post_send_hold_seconds": 0,
        },
    ) == (0.0, 0.0)


# ── validation raises ────────────────────────────────────────────────────────
def test_quic_requires_client_cert() -> None:
    with pytest.raises(ValueError, match="QUIC transport requires"):
        t.TakServerPublisher().publish(
            target=_target(), adapter_config={"transport": "quic", "host": "h"}
        )


def test_mtls_requires_host_then_cert() -> None:
    pub = t.TakServerPublisher()
    with pytest.raises(ValueError, match="requires `host`"):
        pub.publish(target=_target(), adapter_config={})
    with pytest.raises(ValueError, match="client_cert"):
        pub.publish(target=_target(), adapter_config={"host": "h"})


def test_mtls_missing_cert_file_raises() -> None:
    with pytest.raises(FileNotFoundError, match="client_cert"):
        t.TakServerPublisher().publish(
            target=_target(),
            adapter_config={
                "host": "h",
                "client_cert_pem_path": "/nonexistent/c.pem",
                "client_key_pem_path": "/nonexistent/k.pem",
            },
        )


# ── enrollment response parsers ──────────────────────────────────────────────
def test_certs_from_json_orders_leaf_then_chain() -> None:
    leaf, ca = _self_signed(), _self_signed()
    body = (
        b'{"signedCert":"'
        + base64.b64encode(leaf.public_bytes(serialization.Encoding.DER))
        + b'","ca0":"'
        + base64.b64encode(ca.public_bytes(serialization.Encoding.DER))
        + b'"}'
    )
    ders = t._certs_from_json(body)
    assert len(ders) == 2
    assert x509.load_der_x509_certificate(ders[0]).subject == leaf.subject
    assert t._certs_from_json(b"not json") == []
    assert t._certs_from_json(b"[1,2,3]") == []


def test_extract_certs_pem_json_pem_and_pkcs7() -> None:
    leaf = _self_signed()
    der = leaf.public_bytes(serialization.Encoding.DER)
    pem = leaf.public_bytes(serialization.Encoding.PEM)

    # JSON envelope -> PEM
    jbody = b'{"signedCert":"' + base64.b64encode(der) + b'"}'
    assert b"BEGIN CERTIFICATE" in t._extract_certs_pem(jbody)
    # bare PEM passthrough
    assert t._extract_certs_pem(pem) == pem
    # PKCS7 (DER)
    p7_der = pkcs7.serialize_certificates([leaf], serialization.Encoding.DER)
    assert b"BEGIN CERTIFICATE" in t._extract_certs_pem(p7_der)
    # garbage -> RuntimeError
    with pytest.raises(RuntimeError, match="not a recognized"):
        t._extract_certs_pem(b"\x00\x01garbage")


# ── small helpers ────────────────────────────────────────────────────────────
def test_parse_name_entries_handles_namespace_and_garbage() -> None:
    xml = (
        b'<ns2:certificateConfig xmlns="http://bbn.com/marti/xml/config"'
        b' xmlns:ns2="com.bbn.marti.config"><nameEntries>'
        b'<nameEntry name="O" value="none"/><nameEntry name="OU" value="x"/>'
        b"</nameEntries></ns2:certificateConfig>"
    )
    assert t._parse_name_entries(xml) == [("O", "none"), ("OU", "x")]
    assert t._parse_name_entries(b"<broken") == []


def test_build_csr_subject_carries_name_entries() -> None:
    csr_pem, key_pem = t._build_csr("alice", [("O", "none"), ("OU", "ops"), ("CN", "ignored")])
    csr = x509.load_pem_x509_csr(csr_pem)
    rdn = csr.subject.rfc4514_string()
    assert "CN=alice" in rdn and "O=none" in rdn and "OU=ops" in rdn
    assert serialization.load_pem_private_key(key_pem, password=None) is not None


def test_negotiation_request_is_takp_query() -> None:
    xml = t._negotiation_request_xml()
    assert b"t-x-takp-q" in xml and b"TakRequest" in xml
