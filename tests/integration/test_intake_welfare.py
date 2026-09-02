"""Public welfare-check intake (tw-858).

POST /v1/intake/welfare-check (no auth, rate-limited) lets a citizen
submit a welfare-check concern. The submission lands as a Target on
an 'Unmoderated intake' column for the configured intake board.
Operators triage from there.

The endpoint:
  - is unauthenticated (citizens have no account)
  - is rate-limited per source IP
  - validates a minimal payload (address, description, reporter contact)
  - writes the Target with a flag custom_fields.intake_unmoderated=true
  - emits an audit event 'intake.welfare_check.received'

Pre-condition: workspace must have an intake board configured. The
config key 'intake_board_name' on the workspace points at it.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.fast]


def _login(c: TestClient) -> None:
    r = c.post(
        "/v1/auth/login",
        json={"email": "admin@example.com", "password": "test-pw"},  # pragma: allowlist secret
    )
    assert r.status_code == 200, r.text


def _make_intake_board(c: TestClient) -> dict[str, Any]:
    """Create the intake board with the 'Unmoderated intake' column."""
    r = c.post(
        "/v1/boards",
        json={
            "name": "Public Intake",
            "columns": [
                {"name": "Unmoderated intake", "order": 0},
                {"name": "Triaged", "order": 1},
            ],
        },
    )
    assert r.status_code in (200, 201), r.text
    return r.json()


def test_intake_no_auth_required(client: TestClient) -> None:
    _login(client)
    _make_intake_board(client)
    # Use a fresh client without cookies — simulates anonymous citizen.
    client.cookies.clear()
    r = client.post(
        "/v1/intake/welfare-check",
        json={
            "intake_board": "Public Intake",
            "address": "123 Main St, Asheville NC",
            "description": "Cannot reach grandmother since Friday",
            "reporter_name": "Jane D.",
            "reporter_contact": "555-1212",
            "subject_name": "Mary D.",
            "lat": 35.6,
            "lon": -82.55,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "queued"
    assert "id" in body


def test_intake_lands_on_unmoderated_column(client: TestClient) -> None:
    _login(client)
    b = _make_intake_board(client)
    client.cookies.clear()
    r = client.post(
        "/v1/intake/welfare-check",
        json={
            "intake_board": "Public Intake",
            "address": "X",
            "description": "Y",
            "reporter_name": "R",
            "reporter_contact": "555",
            "subject_name": "S",
            "lat": 35.6,
            "lon": -82.55,
        },
    )
    assert r.status_code == 201, r.text
    # Re-auth + verify the target landed on the right column.
    _login(client)
    rows = client.get(
        f"/v1/targets?board_id={b['id']}&column_id={b['columns'][0]['id']}",
    ).json()
    assert len(rows) >= 1
    intake = rows[0]
    assert intake["custom_fields"].get("intake_unmoderated") is True


def test_intake_rejects_unknown_board(client: TestClient) -> None:
    _login(client)
    client.cookies.clear()
    r = client.post(
        "/v1/intake/welfare-check",
        json={
            "intake_board": "DoesNotExist",
            "address": "X",
            "description": "Y",
            "reporter_name": "R",
            "reporter_contact": "555",
            "subject_name": "S",
            "lat": 35.6,
            "lon": -82.55,
        },
    )
    assert r.status_code == 404


def test_intake_rate_limited(client: TestClient) -> None:
    """Per-IP rate limit — burst beyond the budget should 429."""
    _login(client)
    _make_intake_board(client)
    client.cookies.clear()
    payload = {
        "intake_board": "Public Intake",
        "address": "X",
        "description": "Y",
        "reporter_name": "R",
        "reporter_contact": "555",
        "subject_name": "S",
        "lat": 35.6,
        "lon": -82.55,
    }
    # 30 calls in a row from the same IP should hit the limit.
    hit_429 = False
    for _ in range(30):
        r = client.post("/v1/intake/welfare-check", json=payload)
        if r.status_code == 429:
            hit_429 = True
            break
    assert hit_429, "expected at least one 429 within 30 calls"


def test_intake_validates_payload(client: TestClient) -> None:
    _login(client)
    _make_intake_board(client)
    client.cookies.clear()
    r = client.post(
        "/v1/intake/welfare-check",
        json={"intake_board": "Public Intake"},  # missing required fields
    )
    assert r.status_code == 422
