"""Async TCP listener that turns inbound CoT XML into Target rows.

The parser (cot_in.py) is the pure side. This module is the network
+ persistence + realtime-broadcast side. Run one listener per
configured CoT-in SourceConfig.

Wire format: newline-framed XML — one <event>...</event> per line.
This is the convention TAK Server uses on its TCP port (8087 default,
non-TLS) and what our raw_cot publisher emits. TAK Protocol v1
(protobuf) is a separate adapter and is filed as a follow-up.

tw-o13.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlmodel import Session, select

from target_workspace.api.presence import upsert_pli
from target_workspace.api.realtime import get_broker, make_event
from target_workspace.db import get_engine
from target_workspace.db import repositories as repo
from target_workspace.db.tables import UserTable
from target_workspace.models.target import Ellipse, Target
from target_workspace.plugins.sources.cot_in import parse_cot_xml
from target_workspace.workflow.presence import evaluate_presence_workflows

log = logging.getLogger(__name__)


async def run_listener(
    *,
    host: str,
    port: int,
    workspace_id: UUID,
    board_id: UUID,
    column_id: UUID,
    drop_pli: bool = True,
) -> asyncio.base_events.Server:
    """Start an asyncio TCP server listening on `host:port`. Returns
    the Server instance — caller is responsible for `server.close()`
    + `await server.wait_closed()` on shutdown.

    Each incoming connection reads newline-framed CoT XML. Each frame
    is parsed; the resulting dict is materialized as a Target on the
    configured board+column; the realtime broker is notified.

    `drop_pli=True` (default) drops position-location-information
    broadcasts (the high-rate self-pings every ATAK EUD emits). Set
    False for the future presence-tracking use case (tw-lbda)."""

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        peer = writer.get_extra_info("peername")
        log.info("cot-in: connection from %s", peer)
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                stripped = line.strip()
                if not stripped:
                    continue
                _ingest_frame(
                    stripped,
                    workspace_id=workspace_id,
                    board_id=board_id,
                    column_id=column_id,
                    drop_pli=drop_pli,
                )
        except Exception:
            log.exception("cot-in: handler crashed (%s)", peer)
        finally:
            with _suppress():
                writer.close()
                await writer.wait_closed()
            log.info("cot-in: connection closed %s", peer)

    server = await asyncio.start_server(handle, host, port)
    log.info("cot-in: listener bound to %s:%d", host, port)
    return server


def _ingest_frame(
    xml_bytes: bytes,
    *,
    workspace_id: UUID,
    board_id: UUID,
    column_id: UUID,
    drop_pli: bool,
) -> None:
    """Parse one frame; on success create the Target + broadcast.

    Errors are logged + swallowed so one malformed frame doesn't kill
    the listener for the rest of the connection or the next client.
    """
    parsed = parse_cot_xml(xml_bytes)
    if parsed is None:
        log.debug("cot-in: parse failed, dropping frame")
        return
    if parsed.get("_cot_kind") == "pli":
        if drop_pli:
            # Default-drop PLI. tw-lbda will revisit when we want to bind
            # presence to assigned cards.
            return
        _ingest_pli(parsed, workspace_id=workspace_id)
        return

    # Build the Target. Filter out internal hints (_cot_kind) before
    # constructing the model.
    payload = {k: v for k, v in parsed.items() if not k.startswith("_")}
    ellipse = payload.pop("ellipse", None)
    if ellipse is not None:
        payload["ellipse"] = Ellipse(**ellipse)

    try:
        target = Target(**payload)
    except Exception as exc:
        log.warning("cot-in: target construction failed (%s); dropping", exc)
        return

    try:
        with Session(get_engine()) as session:
            session.expire_on_commit = False
            repo.create_target(session, workspace_id, board_id, column_id, target)
            session.commit()
    except Exception:
        log.exception("cot-in: db write failed; dropping frame")
        return

    get_broker().publish(
        workspace_id,
        make_event(
            event_type="target.created",
            workspace_id=workspace_id,
            board_id=board_id,
            target_id=target.id,
            occurred_at=datetime.now(tz=UTC).isoformat(),
            data={"via": "cot_in", "name": target.name},
        ),
    )


def _ingest_pli(parsed: dict[str, Any], *, workspace_id: UUID) -> None:
    upsert_pli(
        callsign=str(parsed["name"]),
        lat=float(parsed["lat"]),
        lon=float(parsed["lon"]),
        hae=parsed.get("hae"),
        ce=parsed.get("ce"),
        le=parsed.get("le"),
        time_iso=parsed["time"].isoformat(),
        source="cot_in",
    )
    try:
        with Session(get_engine()) as session:
            session.expire_on_commit = False
            actor = session.exec(
                select(UserTable).where(UserTable.workspace_id == workspace_id)
            ).first()
            if actor is None:
                return
            result = evaluate_presence_workflows(
                session,
                workspace_id=workspace_id,
                actor_id=actor.id,
                callsign=str(parsed["name"]),
                lat=float(parsed["lat"]),
                lon=float(parsed["lon"]),
                ce=parsed.get("ce"),
                source="cot_in",
            )
            session.commit()
        for outcome in result.outcomes:
            if outcome.nomination_id is None:
                continue
            get_broker().publish(
                workspace_id,
                make_event(
                    event_type="workflow.nominated",
                    workspace_id=workspace_id,
                    target_id=outcome.target_id,
                    occurred_at=datetime.now(tz=UTC).isoformat(),
                    data={"via": "cot_in", **outcome.to_json()},
                ),
            )
    except Exception:
        log.exception("cot-in: PLI workflow failed; dropping frame")


class _suppress:
    """Tiny `contextlib.suppress`-style helper that swallows everything
    so close-and-wait don't crash the handler on a half-closed peer."""

    def __enter__(self) -> _suppress:
        return self

    def __exit__(self, *exc: object) -> bool:
        return True
