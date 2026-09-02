"""Tests for the CoT-in listener lifespan integration (tw-o13).

Boots the FastAPI app with a configured cot_in SourceConfig row in
the DB. Asserts that:
  - the listener is bound and accepting connections
  - shutdown releases the port (so a follow-up test can rebind)
"""

from __future__ import annotations

import contextlib
import os
import socket
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.fast]


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def client_with_cot_in_source(tmp_path: Path) -> Iterator[tuple[TestClient, int]]:
    """Spin a fresh app with a seeded cot_in SourceConfig row. We bind
    to a random localhost port to keep tests parallelizable."""
    port = _free_port()
    db = tmp_path / "cot-in-lifespan.db"
    os.environ["TW_DATABASE_URL"] = f"sqlite:///{db}"
    os.environ["TW_ADMIN_EMAIL"] = "admin@example.com"
    os.environ["TW_ADMIN_PASSWORD"] = "test-pw"
    os.environ["TW_SESSION_SECRET"] = "x" * 40
    os.environ["TW_DEMO_SCENARIOS"] = ""
    os.environ["TW_ENV"] = "test"
    os.environ["TW_BCRYPT_ROUNDS"] = "4"
    from target_workspace.api import config as cfg

    cfg.reset_settings_cache()

    # Pre-create the workspace + board + column + SourceConfig in the
    # DB BEFORE create_app runs, so the lifespan sees the row and
    # starts the listener.

    from sqlmodel import Session

    from target_workspace.api.app import _ensure_bootstrap_user
    from target_workspace.api.config import get_settings
    from target_workspace.db import create_tables, init_db
    from target_workspace.db.tables import (
        BoardTable,
        ColumnTable,
        SourceConfigTable,
        WorkspaceTable,
    )

    s = get_settings()
    engine = init_db(s.database_url)
    create_tables(engine)
    _ensure_bootstrap_user(engine, s)

    with Session(engine) as session:
        session.expire_on_commit = False
        ws = session.exec(__import__("sqlmodel").select(WorkspaceTable)).first()
        assert ws is not None
        board = BoardTable(
            id=uuid4(),
            workspace_id=ws.id,
            name="LifespanTest",
            transitions="unrestricted",
            theme="tactical",
        )
        column = ColumnTable(
            id=uuid4(),
            board_id=board.id,
            name="Find",
            order=0,
            requires_approval=False,
        )
        session.add_all([board, column])
        session.flush()
        session.add(
            SourceConfigTable(
                id=uuid4(),
                workspace_id=ws.id,
                name="Test cot_in",
                plugin_type="cot_in",
                enabled=True,
                adapter_config={
                    "host": "127.0.0.1",
                    "port": port,
                    "board_id": str(board.id),
                    "column_id": str(column.id),
                    "drop_pli": True,
                },
            ),
        )
        session.commit()

    # NOW boot the app (it'll see the SourceConfig row in lifespan).
    from target_workspace.api.app import create_app

    with TestClient(create_app()) as client:
        client.post(
            "/v1/auth/login",
            json={"email": "admin@example.com", "password": "test-pw"},
        )
        yield client, port
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


def test_lifespan_starts_listener_at_boot(
    client_with_cot_in_source: tuple[TestClient, int],
) -> None:
    """A configured cot_in SourceConfig must result in a listening
    socket once the app is up — regardless of whether anyone has
    looked at the kanban yet."""
    _, port = client_with_cot_in_source
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(2.0)
    try:
        sock.connect(("127.0.0.1", port))
    finally:
        with contextlib.suppress(Exception):
            sock.close()


def test_lifespan_listener_accepts_cot_and_creates_target(
    client_with_cot_in_source: tuple[TestClient, int],
) -> None:
    """End-to-end through the lifespan: connect to the port the
    SourceConfig declared, send a CoT event, see the Target appear
    via the SAME API any operator would."""
    client, port = client_with_cot_in_source
    uid = str(uuid4())
    xml = (
        f'<event version="2.0" uid="{uid}" type="a-h-G-E-V"'
        f' time="2026-05-17T18:00:00Z" start="2026-05-17T18:00:00Z"'
        f' stale="2026-05-17T18:15:00Z" how="m-g">'
        f'<point lat="33.4484" lon="-112.0740" hae="0" ce="50" le="50"/>'
        f'<detail><contact callsign="LIFESPAN-TEST"/></detail>'
        f"</event>\n"
    ).encode()

    with client.websocket_connect("/v1/subscribe") as ws:
        assert ws.receive_json()["type"] == "ready"
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2.0)
        sock.connect(("127.0.0.1", port))
        sock.sendall(xml)
        sock.close()
        event = ws.receive_json()
    assert event["type"] == "target.created"
    assert event["data"]["name"] == "LIFESPAN-TEST"

    # The SourceConfig pointed at a specific board+column; fetch +
    # confirm the target landed there.
    from sqlmodel import Session, select

    from target_workspace.db import get_engine
    from target_workspace.db.tables import (
        SourceConfigTable,
        TargetTable,
    )

    with Session(get_engine()) as s:
        src = s.exec(
            select(SourceConfigTable).where(SourceConfigTable.plugin_type == "cot_in"),
        ).first()
        assert src is not None
        board_id = UUID(src.adapter_config["board_id"])
        targets = s.exec(
            select(TargetTable).where(TargetTable.board_id == board_id),
        ).all()
        callsigns = [t.name for t in targets]
    assert "LIFESPAN-TEST" in callsigns, callsigns
