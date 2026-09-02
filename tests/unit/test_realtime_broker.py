"""Unit tests for the in-process realtime Broker.

The Broker is the kernel of the WebSocket fanout: workspace-scoped pub/sub
backed by per-subscriber asyncio.Queues. These tests run it in isolation
(no HTTP, no DB) so a failure here points unambiguously at the broker.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from target_workspace.api.realtime import Broker, make_event


@pytest.mark.fast
@pytest.mark.asyncio
async def test_subscriber_receives_published_event() -> None:
    broker = Broker()
    ws_id = uuid4()
    async with broker.subscribe(ws_id) as events:
        broker.publish(ws_id, {"type": "test.event", "n": 1})
        evt = await asyncio.wait_for(anext(events), timeout=1.0)
    assert evt == {"type": "test.event", "n": 1}


@pytest.mark.fast
@pytest.mark.asyncio
async def test_publish_to_unrelated_workspace_is_dropped() -> None:
    """A subscriber for workspace A must not see workspace B's events."""
    broker = Broker()
    ws_a, ws_b = uuid4(), uuid4()
    async with broker.subscribe(ws_a) as events:
        broker.publish(ws_b, {"type": "leak", "n": 1})
        broker.publish(ws_a, {"type": "ours", "n": 2})
        evt = await asyncio.wait_for(anext(events), timeout=1.0)
    assert evt["type"] == "ours"


@pytest.mark.fast
@pytest.mark.asyncio
async def test_subscriber_unregistered_on_exit() -> None:
    broker = Broker()
    ws_id = uuid4()
    async with broker.subscribe(ws_id):
        assert len(broker._subs[ws_id]) == 1
    # After context exit the workspace key should be gone entirely.
    assert ws_id not in broker._subs


@pytest.mark.fast
@pytest.mark.asyncio
async def test_publish_with_no_subscribers_is_noop() -> None:
    """Publishing to a workspace with no listeners must not raise."""
    broker = Broker()
    broker.publish(uuid4(), {"type": "vacuum"})  # no exception expected


@pytest.mark.fast
@pytest.mark.asyncio
async def test_multiple_subscribers_each_get_each_event() -> None:
    """Fanout, not load-balance: every subscriber for a workspace sees
    every event published to that workspace."""
    broker = Broker()
    ws_id = uuid4()
    async with broker.subscribe(ws_id) as ev_a, broker.subscribe(ws_id) as ev_b:
        broker.publish(ws_id, {"type": "fanout"})
        a = await asyncio.wait_for(anext(ev_a), timeout=1.0)
        b = await asyncio.wait_for(anext(ev_b), timeout=1.0)
    assert a == b == {"type": "fanout"}


@pytest.mark.fast
def test_make_event_envelope_shape() -> None:
    ws, board, target = uuid4(), uuid4(), uuid4()
    evt = make_event(
        event_type="target.created",
        workspace_id=ws,
        board_id=board,
        target_id=target,
        occurred_at="2026-05-17T00:00:00Z",
        data={"name": "BISON-01"},
    )
    assert evt["type"] == "target.created"
    assert evt["workspace_id"] == str(ws)
    assert evt["board_id"] == str(board)
    assert evt["target_id"] == str(target)
    assert evt["occurred_at"] == "2026-05-17T00:00:00Z"
    assert evt["data"]["name"] == "BISON-01"


@pytest.mark.fast
def test_make_event_with_minimal_args() -> None:
    """Optional ids should serialize as None, data defaults to {}."""
    ws = uuid4()
    evt = make_event(
        event_type="board.created",
        workspace_id=ws,
        occurred_at="2026-05-17T00:00:00Z",
    )
    assert evt["board_id"] is None
    assert evt["target_id"] is None
    assert evt["data"] == {}
