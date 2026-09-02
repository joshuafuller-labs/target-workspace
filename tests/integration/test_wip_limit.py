"""WIP-limit enforcement on columns (tw-5i2).

Column.wip_limit is already in the schema. This wires the soft-warning
behavior: moving a target into a column at-or-over its WIP limit
returns a 200 with a 'wip_warning' field, OR if X-Wip-Override header
is missing returns 409.

Soft enforcement per the malleability principle — analyst can override
by re-submitting with X-Wip-Override: true. Audit captures the override.

Assumption documented in tw-5i2:
  - wip_limit applies to MOVE INTO the column, not to current-state
    (an existing card in the column doesn't get evicted when wip_limit
    drops below current count).
  - Without X-Wip-Override → 409 'wip_limit exceeded' on move.
  - With X-Wip-Override: true → 200 + 'wip_warning' field + audit
    metadata { wip_override: true }.
  - wip_limit=None means unlimited (existing behavior).
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.fast]


def _login(c: TestClient) -> None:
    r = c.post(
        "/v1/auth/login",
        json={"email": "admin@example.com", "password": "test-pw"},
    )
    assert r.status_code == 200, r.text


def _make_board_wip(c: TestClient) -> dict[str, Any]:
    return c.post(
        "/v1/boards",
        json={
            "name": "WIP",
            "columns": [
                {"name": "Backlog", "order": 0},
                {"name": "Active", "order": 1, "wip_limit": 2},
            ],
        },
    ).json()


def test_move_into_column_under_limit_succeeds(client: TestClient) -> None:
    _login(client)
    b = _make_board_wip(client)
    backlog = b["columns"][0]["id"]
    active = b["columns"][1]["id"]
    t = client.post(
        "/v1/capture",
        data={
            "title": "T1",
            "lat": "35.6",
            "lon": "-82.55",
            "board_id": b["id"],
            "column_id": backlog,
        },
    ).json()
    r = client.post(
        f"/v1/targets/{t['id']}/move",
        json={"column_id": active, "justification": "first into Active"},
    )
    assert r.status_code == 200, r.text


def test_move_at_or_over_limit_returns_409(client: TestClient) -> None:
    _login(client)
    b = _make_board_wip(client)
    active = b["columns"][1]["id"]
    backlog = b["columns"][0]["id"]
    # Fill Active to 2 (the limit) via captures
    for i in range(2):
        client.post(
            "/v1/capture",
            data={
                "title": f"InActive{i}",
                "lat": str(35.0 + i),
                "lon": str(-82.0 - i),
                "board_id": b["id"],
                "column_id": active,
            },
        )
    # Capture a third in Backlog
    t = client.post(
        "/v1/capture",
        data={
            "title": "ThirdMove",
            "lat": "40.0",
            "lon": "-80.0",
            "board_id": b["id"],
            "column_id": backlog,
        },
    ).json()
    # Try moving the third into Active — should 409
    r = client.post(
        f"/v1/targets/{t['id']}/move",
        json={"column_id": active, "justification": "fail expected"},
    )
    assert r.status_code == 409, r.text


def test_move_with_wip_override_succeeds(client: TestClient) -> None:
    _login(client)
    b = _make_board_wip(client)
    active = b["columns"][1]["id"]
    backlog = b["columns"][0]["id"]
    for i in range(2):
        client.post(
            "/v1/capture",
            data={
                "title": f"InActive{i}",
                "lat": str(40.0 + i),
                "lon": str(-80.0 - i),
                "board_id": b["id"],
                "column_id": active,
            },
        )
    t = client.post(
        "/v1/capture",
        data={
            "title": "ThirdOverride",
            "lat": "50.0",
            "lon": "-70.0",
            "board_id": b["id"],
            "column_id": backlog,
        },
    ).json()
    r = client.post(
        f"/v1/targets/{t['id']}/move",
        json={"column_id": active, "justification": "CDR approved overflow"},
        headers={"X-Wip-Override": "true"},
    )
    assert r.status_code == 200, r.text
