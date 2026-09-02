"""Idempotency-Key header support on POST (tw-54t).

Per ADR 0013: mobile clients on flaky networks can safely retry POST
requests. Server caches the response keyed by (user, endpoint,
Idempotency-Key) for a short window; identical retries return the
original response without re-creating.

Assumption documented in tw-54t:
  - Cache is in-memory (single-instance MVP). Multi-instance needs
    Redis in v1.1.
  - Key namespace: (user_id, path, idempotency_key).
  - TTL: 5 minutes — enough for retry storms on a flaky link, short
    enough that stale responses don't accumulate.
  - First write wins. Concurrent identical-key requests serialize.
  - Body-hash mismatch on the same key returns 409 (prevents key reuse
    across different payloads).
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


def _make_board(c: TestClient) -> dict[str, Any]:
    r = c.post(
        "/v1/boards",
        json={"name": "Idemp", "columns": [{"name": "X", "order": 0}]},
    )
    assert r.status_code == 201
    return r.json()


def test_same_idempotency_key_returns_cached_response(client: TestClient) -> None:
    _login(client)
    board = _make_board(client)
    payload = {
        "title": "T1",
        "lat": "0",
        "lon": "0",
        "board_id": board["id"],
        "column_id": board["columns"][0]["id"],
    }
    headers = {"Idempotency-Key": "test-key-1"}

    r1 = client.post("/v1/capture", data=payload, headers=headers)
    assert r1.status_code == 201
    first_id = r1.json()["id"]

    # Same key + same body → cached response, NO new target created.
    r2 = client.post("/v1/capture", data=payload, headers=headers)
    assert r2.status_code == 201
    assert r2.json()["id"] == first_id


def test_different_idempotency_keys_create_distinct_resources(
    client: TestClient,
) -> None:
    _login(client)
    board = _make_board(client)
    base = {
        "board_id": board["id"],
        "column_id": board["columns"][0]["id"],
    }
    # Use different lat/lon so the correlation engine (find_matching_track)
    # doesn't dedup them into one target.
    r1 = client.post(
        "/v1/capture",
        data={**base, "title": "T-A", "lat": "10.1", "lon": "20.2"},
        headers={"Idempotency-Key": "key-A"},
    )
    r2 = client.post(
        "/v1/capture",
        data={**base, "title": "T-B", "lat": "30.3", "lon": "40.4"},
        headers={"Idempotency-Key": "key-B"},
    )
    assert r1.status_code == 201
    assert r2.status_code == 201
    assert r1.json()["id"] != r2.json()["id"]


def test_post_without_idempotency_key_unaffected(client: TestClient) -> None:
    _login(client)
    board = _make_board(client)
    base = {
        "board_id": board["id"],
        "column_id": board["columns"][0]["id"],
    }
    r1 = client.post(
        "/v1/capture",
        data={**base, "title": "nk-1", "lat": "11.1", "lon": "21.2"},
    )
    r2 = client.post(
        "/v1/capture",
        data={**base, "title": "nk-2", "lat": "31.3", "lon": "41.4"},
    )
    assert r1.status_code == 201
    assert r2.status_code == 201
    # Distinct IDs — no caching when header absent.
    assert r1.json()["id"] != r2.json()["id"]
