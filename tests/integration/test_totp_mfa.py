"""TOTP MFA enrollment + verify-activate + disable (tw-mg1a).

RFC 6238 standard TOTP, implemented with stdlib HMAC + base32. No new
dependency.

Assumption documented in tw-mg1a:
  - MVP scope: enrollment + activation + disable. Login-flow challenge
    (require TOTP after password) is a v1.1 follow-up because it
    changes the cookie payload + dependency contract.
  - Recovery codes (10 single-use) deferred — same v1.1 follow-up.
  - Verify window: +/- 1 timestep (60 seconds total).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.fast]


def _login(c: TestClient) -> None:
    r = c.post(
        "/v1/auth/login",
        json={"email": "admin@example.com", "password": "test-pw"},
    )
    assert r.status_code == 200, r.text


def test_enroll_returns_secret_and_provisioning_uri(client: TestClient) -> None:
    _login(client)
    r = client.post("/v1/auth/mfa/totp/enroll")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "secret" in body
    assert len(body["secret"]) >= 16
    assert body["provisioning_uri"].startswith("otpauth://totp/")


def test_verify_enroll_with_valid_code_activates(client: TestClient) -> None:
    _login(client)
    enroll = client.post("/v1/auth/mfa/totp/enroll").json()
    secret = enroll["secret"]

    # Compute a valid current code from the secret
    from target_workspace.api.totp import generate_code

    code = generate_code(secret)

    r = client.post(
        "/v1/auth/mfa/totp/verify-enroll",
        json={"code": code},
    )
    assert r.status_code == 200, r.text
    assert r.json().get("mfa_enabled") is True

    # /me now reports mfa_enabled
    me = client.get("/v1/auth/me").json()
    assert me.get("mfa_enabled") is True


def test_verify_enroll_with_wrong_code_rejected(client: TestClient) -> None:
    _login(client)
    client.post("/v1/auth/mfa/totp/enroll")
    r = client.post(
        "/v1/auth/mfa/totp/verify-enroll",
        json={"code": "000000"},
    )
    assert r.status_code == 401, r.text


def test_disable_requires_password_and_code(client: TestClient) -> None:
    _login(client)
    secret = client.post("/v1/auth/mfa/totp/enroll").json()["secret"]
    from target_workspace.api.totp import generate_code

    code = generate_code(secret)
    client.post("/v1/auth/mfa/totp/verify-enroll", json={"code": code})

    # Wrong password
    r = client.post(
        "/v1/auth/mfa/totp/disable",
        json={"password": "wrong", "code": generate_code(secret)},
    )
    assert r.status_code == 401, r.text

    # Correct password + code
    r = client.post(
        "/v1/auth/mfa/totp/disable",
        json={"password": "test-pw", "code": generate_code(secret)},
    )
    assert r.status_code == 200, r.text
    me = client.get("/v1/auth/me").json()
    assert me.get("mfa_enabled") is False


def test_endpoints_require_auth(client: TestClient) -> None:
    r = client.post("/v1/auth/mfa/totp/enroll")
    assert r.status_code == 401
