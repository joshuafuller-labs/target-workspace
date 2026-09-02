"""End-to-end WebSocket tests against the real app + real DB.

Verifies the full real-time path: a subscribed client receives a
`target.created` and `target.moved` event when those mutations happen
elsewhere in the API, and an unauthenticated handshake is rejected.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.fast]


def _login(client: TestClient) -> None:
    r = client.post("/v1/auth/login", json={"email": "admin@example.com", "password": "test-pw"})
    assert r.status_code == 200, r.text


def _create_board(client: TestClient) -> dict[str, Any]:
    body = {
        "name": "F3EAD",
        "columns": [
            {"name": "FIND", "order": 0},
            {"name": "FIX", "order": 1},
        ],
    }
    r = client.post("/v1/boards", json=body)
    assert r.status_code == 201, r.text
    out: dict[str, Any] = r.json()
    return out


def _iso_now() -> str:
    return datetime.now(tz=UTC).isoformat()


def test_websocket_rejects_unauthenticated_handshake(client: TestClient) -> None:
    """Without a session cookie, the WS must close with policy-violation."""
    from starlette.websockets import WebSocketDisconnect

    with (
        pytest.raises(WebSocketDisconnect) as exc_info,
        client.websocket_connect("/v1/subscribe") as ws,
    ):
        ws.receive_json()
    # 1008 = policy violation
    assert exc_info.value.code == 1008


def test_websocket_emits_target_created(client: TestClient) -> None:
    _login(client)
    board = _create_board(client)
    find_col = board["columns"][0]

    with client.websocket_connect("/v1/subscribe") as ws:
        ready = ws.receive_json()
        assert ready["type"] == "ready"
        assert ready["workspace_id"]

        r = client.post(
            "/v1/targets",
            json={
                "board_id": board["id"],
                "column_id": find_col["id"],
                "name": "BISON-01",
                "lat": 33.4484,
                "lon": -112.0740,
                "time": _iso_now(),
            },
        )
        assert r.status_code == 201, r.text
        target = r.json()

        # Skip board.created event (fired earlier in the session), then
        # find the target.created
        seen: list[dict[str, Any]] = []
        while True:
            evt = ws.receive_json()
            seen.append(evt)
            if evt["type"] == "target.created":
                break
            if len(seen) > 5:
                raise AssertionError(f"target.created not emitted; saw {seen}")

        assert evt["target_id"] == target["id"]
        assert evt["board_id"] == board["id"]
        assert evt["data"]["name"] == "BISON-01"


def test_websocket_emits_target_moved(client: TestClient) -> None:
    _login(client)
    board = _create_board(client)
    find_col, fix_col = board["columns"][0], board["columns"][1]

    # Create the target before opening the WS so the test only has to wait
    # for one expected event.
    r = client.post(
        "/v1/targets",
        json={
            "board_id": board["id"],
            "column_id": find_col["id"],
            "name": "COBRA-12",
            "lat": 33.4484,
            "lon": -112.0740,
            "time": _iso_now(),
        },
    )
    target = r.json()

    with client.websocket_connect("/v1/subscribe") as ws:
        ws.receive_json()  # ready frame

        r = client.post(
            f"/v1/targets/{target['id']}/move",
            json={"column_id": fix_col["id"], "justification": "cross-cue confirmed"},
        )
        assert r.status_code == 200, r.text

        evt = ws.receive_json()
        assert evt["type"] == "target.moved"
        assert evt["target_id"] == target["id"]
        assert evt["board_id"] == board["id"]
        assert evt["data"]["to_column_id"] == fix_col["id"]
        assert evt["data"]["justification"] == "cross-cue confirmed"


def test_websocket_board_filter_drops_other_boards(client: TestClient) -> None:
    """When the client subscribes with ?board_id=A, events on board B
    must not be delivered."""
    _login(client)
    board_a = _create_board(client)
    # Second board
    r = client.post(
        "/v1/boards",
        json={
            "name": "Other",
            "columns": [
                {"name": "LEAD", "order": 0},
                {"name": "DONE", "order": 1},
            ],
        },
    )
    board_b = r.json()

    with client.websocket_connect(f"/v1/subscribe?board_id={board_a['id']}") as ws:
        ws.receive_json()  # ready

        # Create a target on board B — should NOT arrive on this WS
        client.post(
            "/v1/targets",
            json={
                "board_id": board_b["id"],
                "column_id": board_b["columns"][0]["id"],
                "name": "LEAD-OTHER",
                "lat": 33.0,
                "lon": -112.0,
                "time": _iso_now(),
            },
        )

        # Create a target on board A — SHOULD arrive
        client.post(
            "/v1/targets",
            json={
                "board_id": board_a["id"],
                "column_id": board_a["columns"][0]["id"],
                "name": "ON-BOARD-A",
                "lat": 33.0,
                "lon": -112.0,
                "time": _iso_now(),
            },
        )

        # Drain events; the first target.created we see must be from board A.
        for _ in range(10):
            evt = ws.receive_json()
            if evt["type"] == "target.created":
                assert evt["board_id"] == board_a["id"]
                assert evt["data"]["name"] == "ON-BOARD-A"
                return
        raise AssertionError("no target.created event received for board A")
