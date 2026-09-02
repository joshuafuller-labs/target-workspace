"""Tests for the CoT-in TCP listener (tw-o13).

The parser side is unit-tested in tests/unit/test_cot_parser.py.
This file covers the async listener end-to-end:
  - opens a TCP server on a configured host:port
  - reads newline-framed XML from each connection
  - parses + creates Targets via the same repo path as POST /v1/ingest
  - drops PLI broadcasts by default (configurable)
  - emits realtime broker events

Strategy: spin up the listener on a random localhost port, connect a
plain socket, send a CoT frame, assert the Target row + broker event.
TDD-first.
"""

from __future__ import annotations

import asyncio
import os
import socket
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.fast]


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    db = tmp_path / "cot-in.db"
    os.environ["TW_DATABASE_URL"] = f"sqlite:///{db}"
    os.environ["TW_ADMIN_EMAIL"] = "admin@example.com"
    os.environ["TW_ADMIN_PASSWORD"] = "test-pw"
    os.environ["TW_SESSION_SECRET"] = "x" * 40
    os.environ["TW_DEMO_SCENARIOS"] = ""
    os.environ["TW_ENV"] = "test"
    os.environ["TW_BCRYPT_ROUNDS"] = "4"
    from target_workspace.api import config as cfg

    cfg.reset_settings_cache()
    from target_workspace.api.app import create_app

    with TestClient(create_app()) as c:
        c.post(
            "/v1/auth/login",
            json={"email": "admin@example.com", "password": "test-pw"},
        )
        yield c
    for k in (
        "TW_DATABASE_URL",
        "TW_ADMIN_EMAIL",
        "TW_ADMIN_PASSWORD",
        "TW_SESSION_SECRET",
        "TW_DEMO_SCENARIOS",
        "TW_ENV",
        "TW_BCRYPT_ROUNDS",
    ):
        os.environ.pop(k, None)


def _bootstrap(client: TestClient) -> tuple[UUID, UUID, UUID]:
    """Returns (workspace_id, board_id, column_id) for the listener
    config. We don't go through the SourceConfig DB row in unit tests
    — the listener function takes the IDs as args directly so the
    plumbing layer is testable without alembic + table fixtures."""
    from sqlmodel import Session, select

    from target_workspace.db import get_engine
    from target_workspace.db.tables import WorkspaceTable

    r = client.post(
        "/v1/boards",
        json={"name": "T", "columns": [{"name": "Find", "order": 0}]},
    )
    assert r.status_code == 201
    board = r.json()
    with Session(get_engine()) as s:
        ws = s.exec(select(WorkspaceTable)).first()
        assert ws is not None
        ws_id = ws.id
    return ws_id, UUID(board["id"]), UUID(board["columns"][0]["id"])


def _free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


async def _send_frames_and_wait_for_target_events(
    *,
    port: int,
    workspace_id: UUID,
    frames: bytes,
    count: int,
) -> list[dict[str, Any]]:
    from target_workspace.api.realtime import get_broker

    out: list[dict[str, Any]] = []
    async with get_broker().subscribe(workspace_id) as events:
        _reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(frames)
        await writer.drain()
        writer.close()
        await writer.wait_closed()
        while len(out) < count:
            event = await asyncio.wait_for(anext(events), timeout=2.0)
            if event["type"] == "target.created":
                out.append(event)
    return out


async def _send_frames_and_wait_for_event(
    *,
    port: int,
    workspace_id: UUID,
    frames: bytes,
    event_type: str,
) -> dict[str, Any]:
    from target_workspace.api.realtime import get_broker

    async with get_broker().subscribe(workspace_id) as events:
        _reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(frames)
        await writer.drain()
        writer.close()
        await writer.wait_closed()
        while True:
            event = await asyncio.wait_for(anext(events), timeout=2.0)
            if event["type"] == event_type:
                return event


def _target_listing(
    client: TestClient,
    *,
    board_id: UUID,
    column_id: UUID,
) -> list[dict[str, Any]]:
    listing: list[dict[str, Any]] = client.get(
        f"/v1/targets?board_id={board_id}&column_id={column_id}",
    ).json()
    return listing


def _sample_event_xml(uid: str, callsign: str = "BISON-01") -> bytes:
    return (
        f'<event version="2.0" uid="{uid}" type="a-h-G-E-V"'
        f' time="2026-05-17T18:00:00Z" start="2026-05-17T18:00:00Z"'
        f' stale="2026-05-17T18:15:00Z" how="m-g">'
        f'<point lat="33.4484" lon="-112.0740" hae="0" ce="50" le="50"/>'
        f'<detail><contact callsign="{callsign}"/></detail>'
        "</event>\n"
    ).encode()


def _sample_pli_xml(callsign: str = "MEDIC-1") -> bytes:
    return (
        b'<event version="2.0" uid="ANDROID-medic1" type="a-f-G-U-C-I"'
        b' time="2026-06-05T02:00:00Z" start="2026-06-05T02:00:00Z"'
        b' stale="2026-06-05T02:05:00Z" how="m-g">'
        b'<point lat="35.60001" lon="-82.55000" hae="100" ce="10" le="10"/>'
        + f'<detail><contact callsign="{callsign}"/>'.encode()
        + b'<__group name="Cyan" role="Team Member"/></detail>'
        b"</event>\n"
    )


@pytest.mark.asyncio
async def test_listener_creates_target_from_inbound_cot(
    client: TestClient,
) -> None:
    """End-to-end: start the listener, connect a TCP client, send
    a newline-framed CoT event, assert the Target row appears."""
    from target_workspace.plugins.sources.cot_in_listener import (
        run_listener,
    )

    workspace_id, board_id, column_id = _bootstrap(client)
    port = _free_port()

    server = await run_listener(
        host="127.0.0.1",
        port=port,
        workspace_id=workspace_id,
        board_id=board_id,
        column_id=column_id,
    )
    try:
        events = await _send_frames_and_wait_for_target_events(
            port=port,
            workspace_id=workspace_id,
            frames=_sample_event_xml(str(uuid4())),
            count=1,
        )
        listing = _target_listing(
            client,
            board_id=board_id,
            column_id=column_id,
        )
    finally:
        server.close()
        await server.wait_closed()

    assert [event["data"]["name"] for event in events] == ["BISON-01"]
    assert any(t["name"] == "BISON-01" for t in listing), listing


@pytest.mark.asyncio
async def test_listener_drops_pli_broadcasts_by_default(
    client: TestClient,
) -> None:
    """ATAK EUDs flood the wire with PLI (a-f-G-U-C with __group). A
    listener at default config drops these; otherwise one row per
    self-ping floods the kanban."""
    from target_workspace.plugins.sources.cot_in_listener import (
        run_listener,
    )

    workspace_id, board_id, column_id = _bootstrap(client)
    port = _free_port()

    pli = (
        b'<event version="2.0" uid="ANDROID-deadbeef" type="a-f-G-U-C-I"'
        b' time="2026-05-17T18:00:00Z" start="2026-05-17T18:00:00Z"'
        b' stale="2026-05-17T18:15:00Z" how="m-g">'
        b'<point lat="29.7" lon="-95.4" hae="100" ce="10" le="10"/>'
        b'<detail><contact callsign="Operator-44"/>'
        b'<__group name="Cyan" role="Team Member"/></detail>'
        b"</event>\n"
    )

    server = await run_listener(
        host="127.0.0.1",
        port=port,
        workspace_id=workspace_id,
        board_id=board_id,
        column_id=column_id,
    )
    try:
        events = await _send_frames_and_wait_for_target_events(
            port=port,
            workspace_id=workspace_id,
            frames=pli + _sample_event_xml(str(uuid4()), "SENTINEL"),
            count=1,
        )
        listing = _target_listing(
            client,
            board_id=board_id,
            column_id=column_id,
        )
    finally:
        server.close()
        await server.wait_closed()

    assert [event["data"]["name"] for event in events] == ["SENTINEL"]
    assert sorted(t["name"] for t in listing) == ["SENTINEL"], (
        f"PLI must not produce Targets at default config; got {listing}"
    )


@pytest.mark.asyncio
async def test_listener_routes_pli_to_presence_workflow_when_enabled(
    client: TestClient,
) -> None:
    from sqlmodel import Session, select

    from target_workspace.db import get_engine
    from target_workspace.db.tables import (
        TargetTable,
        WorkflowNominationTable,
        WorkspaceTable,
    )
    from target_workspace.plugins.sources.cot_in_listener import (
        run_listener,
    )

    board_response = client.post(
        "/v1/boards",
        json={
            "name": "SAR",
            "columns": [
                {"name": "Assigned", "order": 0},
                {"name": "On-scene", "order": 1},
            ],
        },
    )
    assert board_response.status_code == 201
    board = board_response.json()
    assigned_col = board["columns"][0]["id"]
    on_scene_col = board["columns"][1]["id"]
    target = client.post(
        "/v1/capture",
        data={
            "title": "Rescue 12",
            "lat": "35.60000",
            "lon": "-82.55000",
            "board_id": board["id"],
            "column_id": assigned_col,
        },
    ).json()
    assign = client.post(f"/v1/targets/{target['id']}/assign", json={"callsign": "MEDIC-1"})
    assert assign.status_code == 200
    trigger = client.post(
        f"/v1/boards/{board['id']}/workflow-triggers",
        json={
            "trigger": "presence.arrived",
            "condition": "min_assignees:1",
            "action_move_to_column_id": on_scene_col,
            "justification_template": "{callsign} arrived",
        },
    )
    assert trigger.status_code == 200
    with Session(get_engine()) as session:
        workspace = session.exec(select(WorkspaceTable)).one()
        workspace_id = workspace.id

    port = _free_port()
    server = await run_listener(
        host="127.0.0.1",
        port=port,
        workspace_id=workspace_id,
        board_id=UUID(board["id"]),
        column_id=UUID(assigned_col),
        drop_pli=False,
    )
    try:
        event = await _send_frames_and_wait_for_event(
            port=port,
            workspace_id=workspace_id,
            frames=_sample_pli_xml("MEDIC-1"),
            event_type="workflow.nominated",
        )
        with Session(get_engine()) as session:
            targets = list(
                session.exec(
                    select(TargetTable).where(TargetTable.board_id == UUID(board["id"]))
                ).all()
            )
            nomination = session.exec(
                select(WorkflowNominationTable).where(
                    WorkflowNominationTable.target_id == UUID(target["id"])
                )
            ).one()
    finally:
        server.close()
        await server.wait_closed()

    assert event["target_id"] == target["id"]
    assert event["data"]["verdict"] == "propose"
    assert event["data"]["nomination_id"] == str(nomination.id)
    assert [row.id for row in targets] == [UUID(target["id"])]
    assert nomination.to_column_id == UUID(on_scene_col)
    assert nomination.proposed_by == f"workflow:presence:{trigger.json()['id']}"
    assert nomination.evidence_json["callsign"] == "MEDIC-1"
    assert nomination.evidence_json["geo_attestation"]["source"] == "cot_in"


@pytest.mark.asyncio
async def test_listener_handles_multiple_frames_on_one_connection(
    client: TestClient,
) -> None:
    """TAK Server can send many events on one TCP connection. The
    listener must accept newline-framed XML and produce one Target
    per frame, not bail after the first."""
    from target_workspace.plugins.sources.cot_in_listener import (
        run_listener,
    )

    workspace_id, board_id, column_id = _bootstrap(client)
    port = _free_port()

    frames = (
        _sample_event_xml("a", "ALPHA")
        + _sample_event_xml("b", "BRAVO")
        + _sample_event_xml("c", "CHARLIE")
    )

    server = await run_listener(
        host="127.0.0.1",
        port=port,
        workspace_id=workspace_id,
        board_id=board_id,
        column_id=column_id,
    )
    try:
        events = await _send_frames_and_wait_for_target_events(
            port=port,
            workspace_id=workspace_id,
            frames=frames,
            count=3,
        )
        listing = _target_listing(
            client,
            board_id=board_id,
            column_id=column_id,
        )
    finally:
        server.close()
        await server.wait_closed()

    assert sorted(event["data"]["name"] for event in events) == ["ALPHA", "BRAVO", "CHARLIE"]
    names = sorted(t["name"] for t in listing)
    assert names == ["ALPHA", "BRAVO", "CHARLIE"], listing


@pytest.mark.asyncio
async def test_listener_ignores_malformed_frames_and_keeps_running(
    client: TestClient,
) -> None:
    """A single bad frame doesn't kill the listener — log + drop +
    continue. Otherwise one TAK client sending malformed XML would
    take the whole bridge down."""
    from target_workspace.plugins.sources.cot_in_listener import (
        run_listener,
    )

    workspace_id, board_id, column_id = _bootstrap(client)
    port = _free_port()

    mixed = (
        b"not xml at all\n"
        + _sample_event_xml("a", "RECOVERS")
        + b"<event broken>\n"
        + _sample_event_xml("b", "STILL-RUNNING")
    )

    server = await run_listener(
        host="127.0.0.1",
        port=port,
        workspace_id=workspace_id,
        board_id=board_id,
        column_id=column_id,
    )
    try:
        events = await _send_frames_and_wait_for_target_events(
            port=port,
            workspace_id=workspace_id,
            frames=mixed,
            count=2,
        )
        listing = _target_listing(
            client,
            board_id=board_id,
            column_id=column_id,
        )
    finally:
        server.close()
        await server.wait_closed()

    assert sorted(event["data"]["name"] for event in events) == ["RECOVERS", "STILL-RUNNING"]
    names = sorted(t["name"] for t in listing)
    assert "RECOVERS" in names and "STILL-RUNNING" in names, listing
