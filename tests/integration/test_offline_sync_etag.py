"""Offline-first sync semantics — version + ETag/If-Match (tw-2j9).

Foundation §15 enabler. Server-issued IDs already exist (uuid4 on
insert). Monotonic version per target already exists. This ticket
exposes that version as an ETag and supports If-Match for optimistic
concurrency control on PATCH — the substrate for offline-first sync
in the mobile MVP.

Assumption documented in tw-2j9:
  - ETag = `W/"v<version>"` weak-validator format.
  - If-Match required for mobile sync clients; absent = no concurrency
    check (back-compat).
  - On mismatch: 412 Precondition Failed.
  - Conflict-resolution hooks (server-side merge rules) defer to the
    actual mobile MVP work; the schema slot is the version column,
    which already exists.
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


def _make_target(c: TestClient) -> dict[str, Any]:
    b = c.post(
        "/v1/boards",
        json={"name": "B", "columns": [{"name": "X", "order": 0}]},
    ).json()
    r = c.post(
        "/v1/capture",
        data={
            "title": "T1",
            "lat": "0",
            "lon": "0",
            "board_id": b["id"],
            "column_id": b["columns"][0]["id"],
        },
    )
    assert r.status_code == 201
    return r.json()


def test_get_target_includes_etag_header(client: TestClient) -> None:
    _login(client)
    t = _make_target(client)
    r = client.get(f"/v1/targets/{t['id']}")
    assert r.status_code == 200
    etag = r.headers.get("ETag")
    assert etag is not None, "GET /v1/targets/{id} must return an ETag"
    assert etag == 'W/"v1"', f"unexpected ETag {etag}"


def test_patch_with_matching_if_match_succeeds(client: TestClient) -> None:
    _login(client)
    t = _make_target(client)
    r = client.patch(
        f"/v1/targets/{t['id']}",
        json={"name": "T1-renamed"},
        headers={"If-Match": 'W/"v1"'},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "T1-renamed"
    assert body["version"] == 2


def test_patch_with_stale_if_match_returns_412(client: TestClient) -> None:
    _login(client)
    t = _make_target(client)
    # First PATCH bumps version to 2
    r = client.patch(
        f"/v1/targets/{t['id']}",
        json={"name": "first"},
    )
    assert r.status_code == 200, r.text
    # Second PATCH with stale If-Match header should fail
    r = client.patch(
        f"/v1/targets/{t['id']}",
        json={"name": "stale"},
        headers={"If-Match": 'W/"v1"'},
    )
    assert r.status_code == 412, r.text


def test_patch_without_if_match_still_succeeds_back_compat(
    client: TestClient,
) -> None:
    _login(client)
    t = _make_target(client)
    r = client.patch(
        f"/v1/targets/{t['id']}",
        json={"name": "no-if-match"},
    )
    assert r.status_code == 200, r.text
