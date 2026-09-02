"""Password reset flow — forgot-password + reset-password (tw-qj9k).

Pluggable email backend (ConsoleEmailBackend default + SmtpEmailBackend
stub). Token sha256-hashed in DB; never logged in plaintext. Rate-limit
rides on tw-b3bi. Successful reset invalidates all existing sessions.

Assumption documented in tw-qj9k:
  - SMTP backend wired but not enabled by default (no env config).
  - ConsoleEmailBackend captures sent messages into an in-memory list
    for tests + dev. Production sites set TW_EMAIL_BACKEND=smtp +
    SMTP_* env vars.
  - Token TTL = 60 minutes. Single-use; subsequent redemption rejects.
  - Returns 202 even for unknown emails to prevent enumeration.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.fast]


def test_forgot_password_known_email_sends_message_with_token(
    client: TestClient,
) -> None:
    r = client.post(
        "/v1/auth/forgot-password",
        json={"email": "admin@example.com"},
    )
    assert r.status_code == 202, r.text

    from target_workspace.api.email import console_outbox

    msgs = console_outbox()
    assert len(msgs) == 1, f"expected 1 outgoing message, got {msgs}"
    assert msgs[0]["to"] == "admin@example.com"
    # Body contains a token suitable for the reset URL
    assert "token=" in (msgs[0].get("body") or "")


def test_forgot_password_unknown_email_still_returns_202(client: TestClient) -> None:
    """Anti-enumeration: identical response regardless of email validity."""
    r = client.post(
        "/v1/auth/forgot-password",
        json={"email": "ghost@example.com"},
    )
    assert r.status_code == 202, r.text

    from target_workspace.api.email import console_outbox

    # No message sent for the unknown email — but the response is identical
    # to the known-email case.
    msgs = console_outbox()
    assert len(msgs) == 0


def test_reset_password_with_valid_token_sets_new_password(
    client: TestClient,
) -> None:
    client.post("/v1/auth/forgot-password", json={"email": "admin@example.com"})
    from target_workspace.api.email import console_outbox

    body = console_outbox()[0]["body"] or ""
    # Token is in the URL as ?token=...
    token = body.split("token=", 1)[1].split()[0].strip()

    r = client.post(
        "/v1/auth/reset-password",
        json={"token": token, "new_password": "freshly-rotated-pw"},
    )
    assert r.status_code == 200, r.text

    # The old password no longer works
    r = client.post(
        "/v1/auth/login",
        json={"email": "admin@example.com", "password": "test-pw"},
    )
    assert r.status_code == 401, r.text
    # The new password works
    r = client.post(
        "/v1/auth/login",
        json={"email": "admin@example.com", "password": "freshly-rotated-pw"},
    )
    assert r.status_code == 200, r.text


def test_reset_password_token_is_single_use(client: TestClient) -> None:
    client.post("/v1/auth/forgot-password", json={"email": "admin@example.com"})
    from target_workspace.api.email import console_outbox

    body = console_outbox()[0]["body"] or ""
    token = body.split("token=", 1)[1].split()[0].strip()

    r1 = client.post(
        "/v1/auth/reset-password",
        json={"token": token, "new_password": "first-rotation"},
    )
    assert r1.status_code == 200

    r2 = client.post(
        "/v1/auth/reset-password",
        json={"token": token, "new_password": "second-rotation"},
    )
    assert r2.status_code == 409, r2.text


def test_reset_password_unknown_token_rejected(client: TestClient) -> None:
    r = client.post(
        "/v1/auth/reset-password",
        json={"token": "z" * 80, "new_password": "x" * 12},
    )
    assert r.status_code == 404, r.text


def test_reset_password_emits_audit_event(client: TestClient) -> None:
    client.post("/v1/auth/forgot-password", json={"email": "admin@example.com"})
    from target_workspace.api.email import console_outbox

    token = console_outbox()[0]["body"].split("token=", 1)[1].split()[0].strip()
    client.post(
        "/v1/auth/reset-password",
        json={"token": token, "new_password": "freshly-rotated"},
    )

    from target_workspace.api.ratelimit import reset_all

    reset_all()
    client.post(
        "/v1/auth/login",
        json={"email": "admin@example.com", "password": "freshly-rotated"},
    )
    raw = client.get("/v1/audit?limit=200").json()
    assert isinstance(raw, list), f"expected list, got {type(raw).__name__}: {raw}"
    reset_events = [
        e
        for e in raw
        if e["event_type"] in ("auth.password.reset.requested", "auth.password.reset.completed")
    ]
    assert len(reset_events) >= 2, (
        f"expected requested + completed audit events, got "
        f"{[e['event_type'] for e in raw if e['event_type'].startswith('auth.')]}"
    )
