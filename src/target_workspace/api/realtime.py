"""In-process pub/sub broker for the realtime WebSocket layer.

The Broker holds per-workspace queues; HTTP routers call `publish()` after
a mutation (target created, target moved, board created), and the
`/v1/subscribe` WebSocket endpoint drains the matching queue and forwards
events to connected clients.

Scope notes
-----------
- In-process only. Single uvicorn worker assumed. Multi-worker requires an
  external broker (Redis pub/sub or NATS) — out of scope for MVP.
- Per-workspace isolation: a subscriber for workspace A never sees events
  from workspace B, enforced by routing on workspace_id at publish-time.
- Sync routers can call `publish()` from the threadpool — the broker
  re-schedules the enqueue back onto the event loop via
  `call_soon_threadsafe`.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID


class Broker:
    """Per-workspace async pub/sub broker."""

    def __init__(self) -> None:
        self._subs: dict[UUID, list[asyncio.Queue[dict[str, Any]]]] = {}
        # Captured lazily on first subscribe — that's when an event loop
        # is guaranteed to be running.
        self._loop: asyncio.AbstractEventLoop | None = None

    def publish(self, workspace_id: UUID, event: dict[str, Any]) -> None:
        """Enqueue an event for every subscriber of the given workspace.

        Safe to call from a thread (sync FastAPI handler) — the actual
        enqueue is scheduled onto the broker's event loop.
        """
        queues = self._subs.get(workspace_id)
        if not queues:
            return
        loop = self._loop
        if loop is None or not loop.is_running():
            # No subscribers' loop captured yet; nothing meaningful to do.
            return
        for q in list(queues):
            loop.call_soon_threadsafe(self._safe_put, q, event)

    @staticmethod
    def _safe_put(queue: asyncio.Queue[dict[str, Any]], event: dict[str, Any]) -> None:
        try:
            queue.put_nowait(event)
        except asyncio.QueueFull:
            # Drop the oldest event to make room for the newest. A slow
            # subscriber doesn't get to back up the publisher.
            with contextlib.suppress(asyncio.QueueEmpty):
                queue.get_nowait()
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(event)

    @contextlib.asynccontextmanager
    async def subscribe(self, workspace_id: UUID) -> AsyncIterator[AsyncIterator[dict[str, Any]]]:
        """Register a subscriber for `workspace_id`; yield an async iterator
        of events. The queue is unregistered on exit.
        """
        # Always (re-)capture the running loop. Subscribe is invoked from
        # the WS endpoint coroutine, so the current running loop is the
        # one we want events delivered on. Re-capturing here also keeps
        # test fixtures honest — each new TestClient session brings up a
        # fresh loop and the broker must follow.
        self._loop = asyncio.get_running_loop()
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=256)
        self._subs.setdefault(workspace_id, []).append(q)

        async def _drain() -> AsyncIterator[dict[str, Any]]:
            while True:
                yield await q.get()

        try:
            yield _drain()
        finally:
            self._subs[workspace_id].remove(q)
            if not self._subs[workspace_id]:
                del self._subs[workspace_id]


# Module-level singleton. The broker is process-wide; a single instance is
# shared by every HTTP request and every active WebSocket.
_broker = Broker()


def get_broker() -> Broker:
    return _broker


def make_event(
    *,
    event_type: str,
    workspace_id: UUID,
    board_id: UUID | None = None,
    target_id: UUID | None = None,
    occurred_at: str,
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a wire-format event envelope.

    Keeping this in one place so the WebSocket payload and the eventual
    OpenAPI/AsyncAPI schema don't drift apart.
    """
    return {
        "type": event_type,
        "occurred_at": occurred_at,
        "workspace_id": str(workspace_id),
        "board_id": str(board_id) if board_id else None,
        "target_id": str(target_id) if target_id else None,
        "data": data or {},
    }
