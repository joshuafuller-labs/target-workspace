"""Suspicious-login detection (tw-huzu).

On every successful login: record client IP + user-agent family.
Compare against this user's prior logins; if first time from this IP
or first time with this UA family, the login is flagged 'suspicious'
in the audit event and a separate 'auth.login.suspicious' event is
emitted so a telemetry view can filter on it.

Defaults conservative — no auto-block.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.fast]


def _login(c: TestClient, ip: str, ua: str) -> int:
    r = c.post(
        "/v1/auth/login",
        json={"email": "admin@example.com", "password": "test-pw"},  # pragma: allowlist secret
        headers={"User-Agent": ua, "X-Forwarded-For": ip},
    )
    return r.status_code


def _audit_events(client: TestClient) -> list[dict[str, Any]]:
    r = client.get("/v1/audit?limit=200")
    assert r.status_code == 200, r.text
    return r.json()


def test_first_login_is_marked_suspicious(client: TestClient) -> None:
    assert _login(client, "10.0.0.1", "Mozilla/5.0 Firefox") == 200
    rows = _audit_events(client)
    success = next(r for r in rows if r["event_type"] == "auth.login.success")
    md = success.get("metadata") or {}
    assert md.get("suspicious") is True
    reasons = md.get("suspicious_reasons", [])
    assert "first_login" in reasons


def test_repeat_login_same_ip_and_ua_is_not_suspicious(client: TestClient) -> None:
    _login(client, "10.0.0.1", "Mozilla/5.0 Firefox")
    _login(client, "10.0.0.1", "Mozilla/5.0 Firefox")
    rows = _audit_events(client)
    successes = [r for r in rows if r["event_type"] == "auth.login.success"]
    assert len(successes) == 2
    # Second one (newest first in the list, so successes[0]) should not be suspicious
    second = successes[0]
    md = second.get("metadata") or {}
    assert md.get("suspicious") is False


def test_new_ip_flagged(client: TestClient) -> None:
    _login(client, "10.0.0.1", "Mozilla/5.0 Firefox")
    _login(client, "10.0.0.2", "Mozilla/5.0 Firefox")
    rows = _audit_events(client)
    second_success = next(r for r in rows if r["event_type"] == "auth.login.success")
    md = second_success["metadata"]
    assert md["suspicious"] is True
    assert "new_ip" in md["suspicious_reasons"]


def test_new_user_agent_flagged(client: TestClient) -> None:
    _login(client, "10.0.0.1", "Mozilla/5.0 Firefox")
    _login(client, "10.0.0.1", "curl/8.7.1")
    rows = _audit_events(client)
    second_success = next(r for r in rows if r["event_type"] == "auth.login.success")
    md = second_success["metadata"]
    assert md["suspicious"] is True
    assert "new_user_agent" in md["suspicious_reasons"]


def test_suspicious_emits_separate_event(client: TestClient) -> None:
    _login(client, "10.0.0.1", "Mozilla/5.0 Firefox")
    rows = _audit_events(client)
    susp = [r for r in rows if r["event_type"] == "auth.login.suspicious"]
    assert len(susp) == 1
