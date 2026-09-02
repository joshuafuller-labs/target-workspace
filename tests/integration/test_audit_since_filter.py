"""Offline-first sync hardening — since-filter on audit log (tw-cjk).

Disaster ops requires a client to pull events since its last sync.
The audit table already persists; this ticket exposes a since=<iso>
query param so clients (mobile, field laptop, tablet) can resume.

Assumption documented in tw-cjk:
  - Conflict-resolution UX (merge dialog on reconnect) is mobile-MVP
    territory. MVP ships the data primitive only.
  - WS event durability beyond audit-log replay is a deeper change;
    audit-log replay is the conservative starting point.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.fast]


def _login(c: TestClient) -> None:
    r = c.post(
        "/v1/auth/login",
        json={"email": "admin@example.com", "password": "test-pw"},
    )
    assert r.status_code == 200, r.text


def test_audit_since_future_returns_empty(client: TestClient) -> None:
    _login(client)
    # Future date — nothing has occurred yet
    future = (datetime.now(tz=UTC) + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    r = client.get(f"/v1/audit?since={future}")
    assert r.status_code == 200, r.text
    assert r.json() == []


def test_audit_since_distant_past_returns_events(client: TestClient) -> None:
    _login(client)
    past = (datetime.now(tz=UTC) - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    r = client.get(f"/v1/audit?since={past}")
    assert r.status_code == 200, r.text
    # The login just now produced an auth.login.success event
    types = {e["event_type"] for e in r.json()}
    assert "auth.login.success" in types


def test_audit_since_invalid_iso_returns_422(client: TestClient) -> None:
    _login(client)
    r = client.get("/v1/audit?since=not-a-date")
    assert r.status_code == 422
