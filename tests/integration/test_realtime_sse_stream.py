"""SSE event-stream + WebSocket branch coverage for the realtime router.

test_sse_events smoke-tests /v1/events via a HEAD request, so the async
event_stream generator body (the `ready` frame, broker subscribe, board
filtering, event yield) and the _resolve_user_workspace valid-session path
were never executed. test_realtime_ws covers the happy WS path but not the
deleted-user rejection or the board-filter drop.

The route handler is invoked directly (it's a coroutine returning a
StreamingResponse) and its body_iterator is driven with asyncio. A real
client.stream() against this endpoint deadlocks the synchronous TestClient —
its context-manager __exit__ can't cancel the still-open async generator — so
direct invocation is the only non-hanging way to read the streamed frames.
This drives _resolve_user_workspace's valid-session branch, the generator
head + response headers, and (by publishing onto the in-process broker) the
event-delivery and board-filter branches.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager, suppress
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.fast]


def _login(c: TestClient) -> UUID:
    r = c.post("/v1/auth/login", json={"email": "admin@example.com", "password": "test-pw"})
    assert r.status_code == 200, r.text
    # The public /me response doesn't expose workspace_id; read it from the DB.
    from sqlmodel import Session, select

    from target_workspace.db import get_engine
    from target_workspace.db.tables import UserTable

    with Session(get_engine()) as session:
        user = session.exec(
            select(UserTable).where(UserTable.email == "admin@example.com"),
        ).first()
        assert user is not None
        return user.workspace_id


# ── SSE: resolve-workspace helper + the route's StreamingResponse ───────
#
# A real client.stream() against this endpoint deadlocks the synchronous
# TestClient (its __exit__ can't cancel the still-open async generator), so
# the route handler is invoked directly: it's a normal coroutine returning a
# StreamingResponse whose body_iterator we can drive with asyncio to read the
# `ready` frame, then close. This covers _resolve_user_workspace's valid path,
# the route head, and the response headers without any streaming deadlock.


def test_resolve_user_workspace_valid_and_invalid(client: TestClient) -> None:
    from target_workspace.api.config import get_settings
    from target_workspace.api.routers.realtime import _resolve_user_workspace

    workspace_id = _login(client)
    settings = get_settings()
    cookie = client.cookies.get(settings.session_cookie_name)
    assert cookie is not None

    # Valid signed session → resolves to the user's workspace.
    assert _resolve_user_workspace({settings.session_cookie_name: cookie}) == workspace_id
    # No cookie at all → None.
    assert _resolve_user_workspace({}) is None
    # Garbage token → invalid signature → None.
    assert _resolve_user_workspace({settings.session_cookie_name: "not.a.valid.token"}) is None


def test_sse_route_emits_ready_frame(client: TestClient) -> None:
    """Invoke the sse_events route handler directly and read its first
    streamed chunk — the `ready` frame — driving the generator head and the
    StreamingResponse construction (headers, media type)."""
    from starlette.requests import Request

    from target_workspace.api.config import get_settings
    from target_workspace.api.routers.realtime import sse_events

    workspace_id = _login(client)
    settings = get_settings()
    cookie = client.cookies.get(settings.session_cookie_name)
    assert cookie is not None

    async def _read_ready() -> str:
        # Minimal ASGI scope carrying the session cookie so
        # _resolve_user_workspace authenticates.
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/v1/events",
            "headers": [(b"cookie", f"{settings.session_cookie_name}={cookie}".encode())],
            "query_string": b"",
        }
        request = Request(scope)
        resp = await sse_events(request, board_id=None, heartbeat_seconds=0)
        assert resp.media_type == "text/event-stream"
        assert resp.headers["cache-control"] == "no-cache"
        assert resp.headers["x-accel-buffering"] == "no"
        agen = cast("AsyncGenerator[str | bytes]", resp.body_iterator)
        try:
            chunk = await agen.__anext__()
        finally:
            await agen.aclose()
        return chunk if isinstance(chunk, str) else chunk.decode()

    frame = asyncio.run(_read_ready())
    assert frame.startswith("event: ready")
    assert str(workspace_id) in frame


def test_sse_route_unauthenticated_raises(client: TestClient) -> None:
    """No session cookie → the route raises 401 before streaming."""
    from fastapi import HTTPException
    from starlette.requests import Request

    from target_workspace.api.routers.realtime import sse_events

    async def _call() -> None:
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/v1/events",
            "headers": [],
            "query_string": b"",
        }
        await sse_events(Request(scope), board_id=None, heartbeat_seconds=0)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(_call())
    assert exc.value.status_code == 401


# ── SSE: drive the generator directly via asyncio ───────────────────────
#
# The event-delivery + board-filter branches block on `await q.get()`, which
# deadlocks the synchronous TestClient if read mid-stream. Driving the same
# code path with asyncio.wait_for against the in-process broker is fast,
# deterministic, and exercises the exact lines (continue / yield).


async def _collect_sse(
    *,
    cookie: str,
    board_id: UUID | None,
    workspace_id: UUID,
    publish: list[dict[str, Any]],
    want: int,
) -> list[str]:
    """Drive the real sse_events route's body_iterator, feed it broker
    events, and collect `want` data frames. Exercises the actual router
    generator (subscribe / board-filter continue / yield)."""
    from starlette.requests import Request

    from target_workspace.api.config import get_settings
    from target_workspace.api.realtime import get_broker
    from target_workspace.api.routers.realtime import sse_events

    settings = get_settings()
    broker = get_broker()

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/v1/events",
        "headers": [(b"cookie", f"{settings.session_cookie_name}={cookie}".encode())],
        "query_string": b"",
    }

    async def _receive() -> dict[str, Any]:
        # The route polls request.is_disconnected(); keep the client
        # "connected" by parking here (is_disconnected cancels the await
        # immediately, so this never actually returns mid-stream).
        return await asyncio.Future()

    resp = await sse_events(
        Request(scope, receive=_receive), board_id=board_id, heartbeat_seconds=0
    )
    agen = cast("AsyncGenerator[str | bytes]", resp.body_iterator)

    out: list[str] = []
    ready = await agen.__anext__()
    ready_str = ready if isinstance(ready, str) else ready.decode()
    assert ready_str.startswith("event: ready")

    # The route's generator enters broker.subscribe() only on the next
    # __anext__. Wrap subscribe so the test can wait on registration directly
    # instead of timing a publish against a sleep.
    original_subscribe = broker.subscribe
    subscribed = asyncio.Event()

    @asynccontextmanager
    async def _notifying_subscribe(
        subscribed_workspace_id: UUID,
    ) -> AsyncIterator[AsyncIterator[dict[str, Any]]]:
        async with original_subscribe(subscribed_workspace_id) as events:
            if subscribed_workspace_id == workspace_id:
                subscribed.set()
            yield events

    setattr(broker, "subscribe", _notifying_subscribe)  # noqa: B010
    next_chunk = asyncio.create_task(agen.__anext__())
    try:
        await asyncio.wait_for(subscribed.wait(), timeout=2.0)
        for ev in publish:
            broker.publish(workspace_id, ev)
        while len(out) < want:
            chunk = await asyncio.wait_for(next_chunk, timeout=2.0)
            out.append(chunk if isinstance(chunk, str) else chunk.decode())
            if len(out) < want:
                next_chunk = asyncio.create_task(agen.__anext__())
    finally:
        if not next_chunk.done():
            next_chunk.cancel()
            with suppress(asyncio.CancelledError):
                await next_chunk
        setattr(broker, "subscribe", original_subscribe)  # noqa: B010
        await agen.aclose()
    return out


def _make_event(workspace_id: UUID, board_id: UUID | None, name: str) -> dict[str, Any]:
    from target_workspace.api.realtime import make_event

    return make_event(
        event_type="target.created",
        workspace_id=workspace_id,
        board_id=board_id,
        occurred_at="2026-05-24T00:00:00+00:00",
        data={"name": name},
    )


def _session_cookie(client: TestClient) -> str:
    from target_workspace.api.config import get_settings

    cookie = client.cookies.get(get_settings().session_cookie_name)
    assert cookie is not None
    return cookie


def test_sse_generator_yields_unfiltered_event(client: TestClient) -> None:
    workspace_id = _login(client)
    cookie = _session_cookie(client)
    ev = _make_event(workspace_id, None, "GHOST-1")
    frames = asyncio.run(
        _collect_sse(
            cookie=cookie,
            board_id=None,
            workspace_id=workspace_id,
            publish=[ev],
            want=1,
        ),
    )
    assert any("GHOST-1" in f and f.startswith("data:") for f in frames)


def test_sse_generator_board_filter_drops_other_board(client: TestClient) -> None:
    workspace_id = _login(client)
    cookie = _session_cookie(client)
    board_a = uuid4()
    board_b = uuid4()
    publish = [
        _make_event(workspace_id, board_b, "OTHER"),  # filtered out
        _make_event(workspace_id, board_a, "ONBOARD-A"),  # delivered
    ]
    frames = asyncio.run(
        _collect_sse(
            cookie=cookie,
            board_id=board_a,
            workspace_id=workspace_id,
            publish=publish,
            want=1,
        ),
    )
    joined = "".join(frames)
    assert "ONBOARD-A" in joined
    assert "OTHER" not in joined


# ── WebSocket branch coverage ───────────────────────────────────────────


def test_ws_rejects_session_for_deleted_user(client: TestClient) -> None:
    """A valid signed cookie whose user row was deleted must close the WS
    with policy-violation — covers the user-is-None branch (lines 112-114)."""
    from sqlmodel import Session, select
    from starlette.websockets import WebSocketDisconnect

    from target_workspace.db import get_engine
    from target_workspace.db.tables import AuditEventTable, UserTable

    _login(client)  # establishes a valid tw_session cookie

    # Delete the admin user row out from under the live session.
    with Session(get_engine()) as session:
        users = session.exec(select(UserTable)).all()
        for u in users:
            audit_rows = session.exec(
                select(AuditEventTable).where(AuditEventTable.actor_id == u.id),
            ).all()
            for audit_row in audit_rows:
                audit_row.actor_id = None
                session.add(audit_row)
            session.flush()
            session.delete(u)
        session.commit()

    with (
        pytest.raises(WebSocketDisconnect) as exc_info,
        client.websocket_connect("/v1/subscribe") as ws,
    ):
        ws.receive_json()
    assert exc_info.value.code == 1008


def test_ws_board_filter_drops_other_board(client: TestClient) -> None:
    """Subscribe filtered to board A; a board-B event must not arrive before
    the board-A event — exercises the WS continue branch (lines 125->exit)."""
    _login(client)

    def _board(name: str) -> dict[str, Any]:
        r = client.post(
            "/v1/boards",
            json={"name": name, "columns": [{"name": "C0", "order": 0}]},
        )
        out: dict[str, Any] = r.json()
        return out

    board_a = _board("A")
    board_b = _board("B")

    with client.websocket_connect(f"/v1/subscribe?board_id={board_a['id']}") as ws:
        ws.receive_json()  # ready

        client.post(
            "/v1/capture",
            data={
                "title": "B-CARD",
                "lat": "10.0",
                "lon": "10.0",
                "board_id": board_b["id"],
                "column_id": board_b["columns"][0]["id"],
            },
        )
        client.post(
            "/v1/capture",
            data={
                "title": "A-CARD",
                "lat": "20.0",
                "lon": "20.0",
                "board_id": board_a["id"],
                "column_id": board_a["columns"][0]["id"],
            },
        )

        for _ in range(10):
            evt = ws.receive_json()
            if evt.get("type") == "target.created":
                assert evt["board_id"] == board_a["id"]
                assert evt["data"]["name"] == "A-CARD"
                break
        else:
            raise AssertionError("board A target.created never arrived")
