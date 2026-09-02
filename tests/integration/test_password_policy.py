"""Password policy enforcement (tw-fn7a).

NIST SP 800-63B-aligned defaults: minimum length only, no composition
requirements, no forced expiry. Settings expose opt-in tightening for
CJIS / FedRAMP environments that mandate stricter rules.

Validation is enforced server-side on every password-setting endpoint:
  - POST /v1/auth/change-password (tw-4exk)
  - POST /v1/auth/reset-password (tw-qj9k)
  - POST /v1/auth/redeem-invitation (tw-qmnh)
  - POST /v1/users (admin-provisioned password)

Assumption documented in tw-fn7a:
  - History (no reuse of last N) and max_age_days (force rotation) are
    deferred to a follow-up; they require a password_history table and
    a rotation-check middleware. MVP ships length + complexity knobs.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.fast]


@pytest.fixture
def client() -> Iterator[TestClient]:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as dbfile:
        db_path = dbfile.name
    os.environ["TW_DATABASE_URL"] = f"sqlite:///{db_path}"
    os.environ["TW_ADMIN_EMAIL"] = "admin@example.com"
    os.environ["TW_ADMIN_PASSWORD"] = "test-pw-long-enough"
    os.environ["TW_SESSION_SECRET"] = "test-secret-test-secret-test-secret"
    # Tighten the policy for this test run.
    os.environ["TW_PASSWORD_MIN_LENGTH"] = "12"

    from target_workspace.api import config as config_module

    config_module.reset_settings_cache()
    from target_workspace.api.app import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c

    os.unlink(db_path)
    for k in (
        "TW_DATABASE_URL",
        "TW_ADMIN_EMAIL",
        "TW_ADMIN_PASSWORD",
        "TW_SESSION_SECRET",
        "TW_PASSWORD_MIN_LENGTH",
    ):
        os.environ.pop(k, None)
    config_module.reset_settings_cache()


def _login_admin(c: TestClient) -> None:
    r = c.post(
        "/v1/auth/login",
        json={"email": "admin@example.com", "password": "test-pw-long-enough"},
    )
    assert r.status_code == 200, r.text


def test_short_password_rejected_on_user_create(client: TestClient) -> None:
    _login_admin(client)
    r = client.post(
        "/v1/users",
        json={
            "email": "shorty@example.com",
            "display_name": "Short",
            "role": "viewer",
            "password": "short",
        },
    )
    assert r.status_code == 422, r.text
    assert "password" in r.json().get("detail", "").lower()


def test_long_enough_password_accepted_on_user_create(client: TestClient) -> None:
    _login_admin(client)
    r = client.post(
        "/v1/users",
        json={
            "email": "longer@example.com",
            "display_name": "Longer",
            "role": "viewer",
            "password": "this-is-long-enough",
        },
    )
    assert r.status_code == 201, r.text


def test_short_new_password_rejected_on_change_password(client: TestClient) -> None:
    _login_admin(client)
    # Admin's own change-password attempt with a too-short new
    r = client.post(
        "/v1/auth/change-password",
        json={"current_password": "test-pw-long-enough", "new_password": "tiny"},
    )
    assert r.status_code == 422, r.text


def test_short_new_password_rejected_on_reset_password(client: TestClient) -> None:
    client.post("/v1/auth/forgot-password", json={"email": "admin@example.com"})
    from target_workspace.api.email import console_outbox

    msgs = console_outbox()
    assert msgs, "expected forgot-password email"
    token = msgs[0]["body"].split("token=", 1)[1].split()[0].strip()

    r = client.post(
        "/v1/auth/reset-password",
        json={"token": token, "new_password": "tiny"},
    )
    assert r.status_code == 422, r.text


def test_short_password_rejected_on_invitation_redeem(client: TestClient) -> None:
    _login_admin(client)
    inv = client.post("/v1/invitations", json={"role": "viewer"}).json()
    client.post("/v1/auth/logout")
    r = client.post(
        "/v1/auth/redeem-invitation",
        json={
            "token": inv["token"],
            "email": "redeemed@example.com",
            "display_name": "Redeemed",
            "password": "tiny",
        },
    )
    assert r.status_code == 422, r.text
