"""WebSocket subscribe + SSE fallback — real-time board updates.

Per ADR 0013 the primary realtime path is a topic-filtered WebSocket;
tw-peh adds a Server-Sent Events fallback at /v1/events for clients
behind proxies that strip the WS upgrade. Both share auth + filter
semantics.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, WebSocket, WebSocketDisconnect, status
from fastapi.responses import StreamingResponse
from sqlmodel import Session, select

from target_workspace.api.auth import verify_session
from target_workspace.api.config import get_settings
from target_workspace.api.realtime import get_broker
from target_workspace.db import get_engine
from target_workspace.db.tables import UserTable

router = APIRouter()


def _resolve_user_workspace(request_cookies: dict[str, str]) -> UUID | None:
    """Resolve workspace_id from the signed session cookie. Returns None
    if no valid session is attached."""
    settings = get_settings()
    token = request_cookies.get(settings.session_cookie_name)
    if not token:
        return None
    user_id = verify_session(token, settings.session_secret)
    if user_id is None:
        return None
    with Session(get_engine()) as session:
        user = session.exec(select(UserTable).where(UserTable.id == user_id)).first()
        if user is None:
            return None
        return user.workspace_id


@router.get("/v1/events")
async def sse_events(
    request: Request,
    board_id: UUID | None = Query(default=None),
    heartbeat_seconds: int = Query(default=20, ge=0, le=600),
) -> StreamingResponse:
    """SSE fallback for clients behind WS-stripping proxies (tw-peh).

    Same workspace scoping as /v1/subscribe. Heartbeat comments keep
    long-poll-aware proxies from idle-closing the connection; set
    heartbeat_seconds=0 to disable.
    """
    workspace_id = _resolve_user_workspace(dict(request.cookies))
    if workspace_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing or invalid session",
        )

    async def event_stream() -> AsyncIterator[str]:
        yield f"event: ready\ndata: {json.dumps({'workspace_id': str(workspace_id)})}\n\n"
        broker = get_broker()
        async with broker.subscribe(workspace_id) as events:
            async for event in events:
                if await request.is_disconnected():
                    return
                if board_id is not None and event.get("board_id") not in (
                    None,
                    str(board_id),
                ):
                    continue
                yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable nginx response buffering
        },
    )


@router.websocket("/v1/subscribe")
async def subscribe(
    websocket: WebSocket,
    board_id: UUID | None = Query(default=None),
) -> None:
    """Stream realtime events for the current user's workspace.

    Query params:
        board_id: optional; when set, events for other boards are filtered
                  out server-side so a noisy workspace doesn't flood a
                  client that only cares about one board.
    """
    settings = get_settings()
    token = websocket.cookies.get("tw_session")
    user_id = verify_session(token, settings.session_secret) if token else None
    if user_id is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Resolve the user's workspace once at handshake; subsequent events are
    # routed by workspace_id, never by the cookie. A revoked session can't
    # eavesdrop past its disconnect.
    with Session(get_engine()) as session:
        user = session.exec(select(UserTable).where(UserTable.id == user_id)).first()
        if user is None:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        workspace_id = user.workspace_id

    await websocket.accept()
    # Send a ready frame so clients can distinguish "subscribed" from
    # "connection accepted but waiting for first event".
    await websocket.send_json({"type": "ready", "workspace_id": str(workspace_id)})

    broker = get_broker()
    async with broker.subscribe(workspace_id) as events:
        try:
            async for event in events:
                if board_id is not None and event.get("board_id") not in (
                    None,
                    str(board_id),
                ):
                    continue
                await websocket.send_json(event)
        except WebSocketDisconnect:
            return
