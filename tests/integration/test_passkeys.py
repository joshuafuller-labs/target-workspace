"""WebAuthn/passkey ceremonies."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.fast]

CREDENTIAL_ID = "Y3JlZGVudGlhbC1pZA"


@pytest.fixture
def client() -> Iterator[TestClient]:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as dbfile:
        db_path = dbfile.name
    os.environ["TW_DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["TW_ADMIN_EMAIL"] = "admin@example.com"
    os.environ["TW_ADMIN_PASSWORD"] = "test-pw"  # pragma: allowlist secret
    os.environ["TW_SESSION_SECRET"] = (
        "test-secret-test-secret-test-secret"  # pragma: allowlist secret
    )
    os.environ["TW_WEBAUTHN_RP_ID"] = "testserver"
    os.environ["TW_WEBAUTHN_ORIGIN"] = "http://testserver"

    from target_workspace.api import config as config_module

    config_module.reset_settings_cache()
    from target_workspace.api.app import create_app

    app = create_app()
    with TestClient(app, base_url="http://testserver") as c:
        yield c

    os.unlink(db_path)
    for key in (
        "TW_DATABASE_URL",
        "TW_ADMIN_EMAIL",
        "TW_ADMIN_PASSWORD",
        "TW_SESSION_SECRET",
        "TW_WEBAUTHN_RP_ID",
        "TW_WEBAUTHN_ORIGIN",
    ):
        os.environ.pop(key, None)
    config_module.reset_settings_cache()


def _login(client: TestClient) -> None:
    response = client.post(
        "/v1/auth/login",
        json={"email": "admin@example.com", "password": "test-pw"},  # pragma: allowlist secret
    )
    assert response.status_code == 200, response.text


@dataclass(frozen=True)
class FakeRegistration:
    credential_id: bytes = b"credential-id"
    credential_public_key: bytes = b"public-key"
    sign_count: int = 7
    aaguid: str = "00000000-0000-0000-0000-000000000000"


@dataclass(frozen=True)
class FakeAuthentication:
    credential_id: bytes = b"credential-id"
    new_sign_count: int = 8


def test_register_passkey_and_reject_challenge_replay(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _login(client)
    options_response = client.post(
        "/v1/auth/passkeys/register/options",
        json={"name": "Laptop"},
    )
    assert options_response.status_code == 200, options_response.text
    challenge = options_response.json()["publicKey"]["challenge"]

    import target_workspace.api.routers.passkeys as passkeys_router

    def fake_verify_registration_response(**kwargs: object) -> FakeRegistration:
        assert kwargs["expected_rp_id"] == "testserver"
        assert kwargs["expected_origin"] == "http://testserver"
        assert kwargs["expected_challenge"]
        return FakeRegistration()

    monkeypatch.setattr(
        passkeys_router,
        "verify_registration_response",
        fake_verify_registration_response,
    )

    verify_response = client.post(
        "/v1/auth/passkeys/register/verify",
        json={"name": "Laptop", "challenge": challenge, "credential": {"id": CREDENTIAL_ID}},
    )
    assert verify_response.status_code == 201, verify_response.text
    assert verify_response.json()["name"] == "Laptop"

    replay_response = client.post(
        "/v1/auth/passkeys/register/verify",
        json={"name": "Laptop", "challenge": challenge, "credential": {"id": CREDENTIAL_ID}},
    )
    assert replay_response.status_code == 409

    listed = client.get("/v1/auth/passkeys").json()
    assert [item["name"] for item in listed] == ["Laptop"]

    audit_events = client.get("/v1/audit").json()
    registration = next(
        event
        for event in audit_events
        if event["event_type"] == "auth.passkey.registration.success"
    )
    assert registration["metadata"]["method"] == "passkey"
    assert registration["metadata"]["email"] == "admin@example.com"
    assert registration["metadata"]["passkey_name"] == "Laptop"
    assert registration["metadata"]["passkey_id"] == verify_response.json()["id"]
    assert "credential_id" not in registration["metadata"]


def test_failed_passkey_registration_writes_safe_audit_event(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _login(client)
    options_response = client.post(
        "/v1/auth/passkeys/register/options",
        json={"name": "Laptop"},
    )
    assert options_response.status_code == 200, options_response.text
    challenge = options_response.json()["publicKey"]["challenge"]

    import target_workspace.api.routers.passkeys as passkeys_router

    def fail_verify_registration_response(**_: object) -> FakeRegistration:
        raise ValueError("bad attestation")

    monkeypatch.setattr(
        passkeys_router,
        "verify_registration_response",
        fail_verify_registration_response,
    )

    verify_response = client.post(
        "/v1/auth/passkeys/register/verify",
        json={"name": "Laptop", "challenge": challenge, "credential": {"id": CREDENTIAL_ID}},
    )
    assert verify_response.status_code == 400, verify_response.text

    audit_events = client.get("/v1/audit").json()
    registration = next(
        event for event in audit_events if event["event_type"] == "auth.passkey.registration.failed"
    )
    assert registration["metadata"]["method"] == "passkey"
    assert registration["metadata"]["email"] == "admin@example.com"
    assert registration["metadata"]["passkey_name"] == "Laptop"
    assert registration["metadata"]["reason"] == "invalid_passkey"
    assert "credential_id" not in registration["metadata"]


def test_discoverable_passkey_login_sets_session_cookie(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _login(client)
    import target_workspace.api.routers.passkeys as passkeys_router

    monkeypatch.setattr(
        passkeys_router,
        "verify_registration_response",
        lambda **_: FakeRegistration(),
    )
    register_options = client.post(
        "/v1/auth/passkeys/register/options",
        json={"name": "Phone"},
    ).json()
    client.post(
        "/v1/auth/passkeys/register/verify",
        json={
            "name": "Phone",
            "challenge": register_options["publicKey"]["challenge"],
            "credential": {"id": CREDENTIAL_ID},
        },
    )
    client.post("/v1/auth/logout")

    auth_options = client.post("/v1/auth/passkeys/authenticate/options").json()
    assert "allowCredentials" not in auth_options["publicKey"]

    def fake_verify_authentication_response(**kwargs: object) -> FakeAuthentication:
        assert_authentication_expectations(kwargs)
        return FakeAuthentication()

    monkeypatch.setattr(
        passkeys_router,
        "verify_authentication_response",
        fake_verify_authentication_response,
    )
    auth_response = client.post(
        "/v1/auth/passkeys/authenticate/verify",
        json={
            "challenge": auth_options["publicKey"]["challenge"],
            "credential": {"id": CREDENTIAL_ID},
        },
    )
    assert auth_response.status_code == 200, auth_response.text
    assert auth_response.json()["email"] == "admin@example.com"
    assert client.cookies.get("tw_session")
    audit_events = client.get("/v1/audit").json()
    passkey_login = next(
        event
        for event in audit_events
        if event["event_type"] == "auth.login.success"
        and event["metadata"].get("method") == "passkey"
    )
    assert passkey_login["metadata"]["email"] == "admin@example.com"
    assert passkey_login["metadata"]["passkey_name"] == "Phone"
    assert "credential_id" not in passkey_login["metadata"]


def test_failed_passkey_login_writes_safe_audit_event(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _login(client)
    import target_workspace.api.routers.passkeys as passkeys_router

    monkeypatch.setattr(
        passkeys_router,
        "verify_registration_response",
        lambda **_: FakeRegistration(),
    )
    register_options = client.post(
        "/v1/auth/passkeys/register/options",
        json={"name": "Phone"},
    ).json()
    client.post(
        "/v1/auth/passkeys/register/verify",
        json={
            "name": "Phone",
            "challenge": register_options["publicKey"]["challenge"],
            "credential": {"id": CREDENTIAL_ID},
        },
    )
    client.post("/v1/auth/logout")

    auth_options = client.post("/v1/auth/passkeys/authenticate/options").json()

    def fail_verify_authentication_response(**_: object) -> FakeAuthentication:
        raise ValueError("bad assertion")

    monkeypatch.setattr(
        passkeys_router,
        "verify_authentication_response",
        fail_verify_authentication_response,
    )
    auth_response = client.post(
        "/v1/auth/passkeys/authenticate/verify",
        json={
            "challenge": auth_options["publicKey"]["challenge"],
            "credential": {"id": CREDENTIAL_ID},
        },
    )
    assert auth_response.status_code == 401, auth_response.text

    _login(client)
    audit_events = client.get("/v1/audit").json()
    passkey_failure = next(
        event
        for event in audit_events
        if event["event_type"] == "auth.login.failed"
        and event["metadata"].get("method") == "passkey"
    )
    assert passkey_failure["metadata"]["email"] == "admin@example.com"
    assert passkey_failure["metadata"]["reason"] == "invalid_passkey"
    assert passkey_failure["metadata"]["passkey_name"] == "Phone"
    assert "credential_id" not in passkey_failure["metadata"]


def test_passkey_login_normalizes_padded_credential_id(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _login(client)
    import target_workspace.api.routers.passkeys as passkeys_router

    monkeypatch.setattr(
        passkeys_router,
        "verify_registration_response",
        lambda **_: FakeRegistration(),
    )
    register_options = client.post(
        "/v1/auth/passkeys/register/options",
        json={"name": "Bitwarden"},
    ).json()
    client.post(
        "/v1/auth/passkeys/register/verify",
        json={
            "name": "Bitwarden",
            "challenge": register_options["publicKey"]["challenge"],
            "credential": {"id": CREDENTIAL_ID},
        },
    )
    client.post("/v1/auth/logout")

    auth_options = client.post("/v1/auth/passkeys/authenticate/options").json()

    def fake_verify_authentication_response(**kwargs: object) -> FakeAuthentication:
        assert_authentication_expectations(kwargs)
        return FakeAuthentication()

    monkeypatch.setattr(
        passkeys_router,
        "verify_authentication_response",
        fake_verify_authentication_response,
    )
    auth_response = client.post(
        "/v1/auth/passkeys/authenticate/verify",
        json={
            "challenge": auth_options["publicKey"]["challenge"],
            "credential": {"id": f"{CREDENTIAL_ID}=="},
        },
    )

    assert auth_response.status_code == 200, auth_response.text


def test_passkey_verification_uses_forwarded_https_origin_when_not_configured(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import os

    import target_workspace.api.routers.passkeys as passkeys_router
    from target_workspace.api import config as config_module

    os.environ.pop("TW_WEBAUTHN_RP_ID", None)
    os.environ.pop("TW_WEBAUTHN_ORIGIN", None)
    config_module.reset_settings_cache()

    _login(client)
    options = client.post(
        "/v1/auth/passkeys/register/options",
        json={"name": "Dogfood"},
        headers={
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Host": "workspace.example.com",
        },
    ).json()

    def fake_verify_registration_response(**kwargs: object) -> FakeRegistration:
        assert kwargs["expected_rp_id"] == "workspace.example.com"
        assert kwargs["expected_origin"] == "https://workspace.example.com"
        return FakeRegistration()

    monkeypatch.setattr(
        passkeys_router,
        "verify_registration_response",
        fake_verify_registration_response,
    )

    response = client.post(
        "/v1/auth/passkeys/register/verify",
        json={
            "name": "Dogfood",
            "challenge": options["publicKey"]["challenge"],
            "credential": {"id": CREDENTIAL_ID},
        },
        headers={
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Host": "workspace.example.com",
        },
    )

    assert response.status_code == 201, response.text


def assert_authentication_expectations(kwargs: dict[str, object]) -> None:
    assert kwargs["expected_rp_id"] == "testserver"
    assert kwargs["expected_origin"] == "http://testserver"
    assert kwargs["credential_current_sign_count"] == 7


def test_delete_passkey_revokes_credential(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _login(client)
    import target_workspace.api.routers.passkeys as passkeys_router

    monkeypatch.setattr(
        passkeys_router,
        "verify_registration_response",
        lambda **_: FakeRegistration(),
    )
    options = client.post("/v1/auth/passkeys/register/options", json={"name": "Key"}).json()
    created = client.post(
        "/v1/auth/passkeys/register/verify",
        json={
            "name": "Key",
            "challenge": options["publicKey"]["challenge"],
            "credential": {"id": CREDENTIAL_ID},
        },
    ).json()

    response = client.delete(f"/v1/auth/passkeys/{UUID(created['id'])}")
    assert response.status_code == 204
    assert client.get("/v1/auth/passkeys").json() == []
