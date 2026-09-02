"""Tests for scenario discovery + seed_workspace (TDD chunk for tw-ebv / tw-d5v)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlmodel import select

from target_workspace.api.auth import hash_password
from target_workspace.db import create_engine_for_url, create_tables, get_session
from target_workspace.db.tables import (
    AuditEventTable,
    BoardTable,
    PublisherConfigTable,
    TargetTable,
    UserTable,
    WorkspaceTable,
)
from target_workspace.demo import discover_scenarios, seed_workspace

pytestmark = [pytest.mark.fast]


@pytest.fixture
def engine() -> Iterator[Any]:
    eng = create_engine_for_url("sqlite:///:memory:")
    create_tables(eng)
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture
def admin_workspace(engine: Any) -> Any:
    with get_session(engine) as session:
        ws = WorkspaceTable(name="Default", created_at=datetime.now(tz=UTC))
        session.add(ws)
        session.flush()
        user = UserTable(
            workspace_id=ws.id,
            email="admin@example.com",
            display_name="Admin",
            role="admin",
            password_hash=hash_password("x"),
            created_at=datetime.now(tz=UTC),
        )
        session.add(user)
        session.commit()
        return ws.id


def test_discover_finds_bundled_scenarios() -> None:
    scenarios = discover_scenarios()
    expected = {
        "tf-dagger-f3ead",
        "le-counter-narco",
        "sar-missing-hiker",
        "disaster-relief-hurricane",
    }
    assert expected.issubset(set(scenarios.keys()))


def test_seed_workspace_creates_board_and_targets(engine: Any, admin_workspace: Any) -> None:
    result = seed_workspace(engine, scenario_id="tf-dagger-f3ead")
    assert result["status"] == "seeded"
    assert result["targets_created"] >= 10
    assert result["transitions_replayed"] >= 5
    assert result["publishers_created"]

    with get_session(engine) as session:
        boards = session.exec(
            select(BoardTable).where(BoardTable.workspace_id == admin_workspace)
        ).all()
        assert any(b.name == "F3EAD" for b in boards)

        targets = session.exec(
            select(TargetTable).where(TargetTable.workspace_id == admin_workspace)
        ).all()
        names = {t.name for t in targets}
        assert "BISON-01" in names
        assert "EAGLE-31" in names

        audit = session.exec(
            select(AuditEventTable).where(AuditEventTable.workspace_id == admin_workspace)
        ).all()
        assert len(audit) >= len(targets)  # at least one event per target

        pubs = session.exec(
            select(PublisherConfigTable).where(PublisherConfigTable.workspace_id == admin_workspace)
        ).all()
        assert any(p.plugin_type == "raw_cot" for p in pubs)


def test_seed_workspace_is_idempotent_on_board_name(engine: Any, admin_workspace: Any) -> None:
    seed_workspace(engine, scenario_id="tf-dagger-f3ead")
    second = seed_workspace(engine, scenario_id="tf-dagger-f3ead")
    assert second["status"] == "already-seeded"


def test_seed_multiple_scenarios_share_workspace(engine: Any, admin_workspace: Any) -> None:
    """All four scenarios coexist as separate boards in the same workspace."""
    for sid in [
        "tf-dagger-f3ead",
        "le-counter-narco",
        "sar-missing-hiker",
        "disaster-relief-hurricane",
    ]:
        seed_workspace(engine, scenario_id=sid)

    with get_session(engine) as session:
        boards = session.exec(
            select(BoardTable).where(BoardTable.workspace_id == admin_workspace)
        ).all()
        board_names = {b.name for b in boards}
        assert {"F3EAD", "Case Board", "SAR · Missing Person", "Incident Response"}.issubset(
            board_names
        )
