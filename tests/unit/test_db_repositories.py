"""Tests for the persistence layer (TDD chunk 6).

Uses in-memory SQLite — fast, no external dependencies, single-process.
Real Postgres + PostGIS integration tests live in tests/integration/.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import event

from target_workspace.db import create_engine_for_url, create_tables, get_session
from target_workspace.db.repositories import (
    create_board,
    create_promotion_policy,
    create_target,
    create_workspace,
    get_board,
    get_promotion_policy,
    get_target,
    get_workspace,
    list_targets_in_column,
    list_targets_on_board,
    move_target_to_column,
)
from target_workspace.db.tables import TrackObservationTable
from target_workspace.models.board import Board, Column
from target_workspace.models.promotion_policy import PromotionPolicy
from target_workspace.models.target import Target

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
def board(engine: Any) -> Board:
    with get_session(engine) as session:
        ws = create_workspace(session, name="Personal")
        b = Board(
            name="F3EAD",
            columns=[
                Column(name="FIND", order=0),
                Column(name="FIX", order=1),
                Column(name="FINISH", order=2),
            ],
        )
        create_board(session, ws.id, b)
        return b


def _target_kwargs() -> dict[str, Any]:
    return {
        "name": "BISON-01",
        "lat": 33.4484,
        "lon": -112.0740,
        "time": datetime(2026, 5, 16, 21, 45, 0, tzinfo=UTC),
    }


class TestWorkspace:
    def test_round_trip(self, engine: Any) -> None:
        with get_session(engine) as session:
            ws = create_workspace(session, name="Personal")
        with get_session(engine) as session:
            assert get_workspace(session, ws.id) is not None


class TestBoard:
    def test_round_trip_preserves_columns(self, engine: Any, board: Board) -> None:
        with get_session(engine) as session:
            stored = get_board(session, board.id)
        assert stored is not None
        assert stored.name == board.name
        assert [c.name for c in stored.columns] == ["FIND", "FIX", "FINISH"]
        assert [c.order for c in stored.columns] == [0, 1, 2]

    def test_get_missing_returns_none(self, engine: Any) -> None:
        from uuid import uuid4

        with get_session(engine) as session:
            assert get_board(session, uuid4()) is None


class TestPromotionPolicy:
    def test_round_trip_gated(self, engine: Any) -> None:
        with get_session(engine) as session:
            ws = create_workspace(session, name="Personal")
            policy = PromotionPolicy(mode="gated", approval_roles=["analyst", "supervisor"])
            create_promotion_policy(session, ws.id, policy)
        with get_session(engine) as session:
            stored = get_promotion_policy(session, policy.id)
        assert stored is not None
        assert stored.mode == "gated"
        assert stored.approval_roles == ["analyst", "supervisor"]


class TestTarget:
    def test_round_trip(self, engine: Any, board: Board) -> None:
        target = Target(**_target_kwargs())
        with get_session(engine) as session:
            ws = create_workspace(session, name="WS2")
            create_target(session, ws.id, board.id, board.columns[0].id, target)
        with get_session(engine) as session:
            stored = get_target(session, target.id)
        assert stored is not None
        assert stored.name == "BISON-01"
        assert stored.lat == pytest.approx(33.4484)
        assert stored.version == 1

    def test_list_targets_on_board(self, engine: Any, board: Board) -> None:
        with get_session(engine) as session:
            ws = create_workspace(session, name="WS3")
            for i in range(3):
                t = Target(**{**_target_kwargs(), "name": f"T-{i}"})
                create_target(session, ws.id, board.id, board.columns[0].id, t)
        with get_session(engine) as session:
            assert len(list_targets_on_board(session, board.id)) == 3

    def test_list_targets_on_board_batches_confidence_chains(
        self,
        engine: Any,
        board: Board,
    ) -> None:
        target_count = 5
        with get_session(engine) as session:
            ws = create_workspace(session, name="WS3B")
            for i in range(target_count):
                t = Target(**{**_target_kwargs(), "name": f"T-{i}", "source": f"sensor-{i}"})
                row = create_target(session, ws.id, board.id, board.columns[0].id, t)
                session.add(
                    TrackObservationTable(
                        id=uuid4(),
                        workspace_id=ws.id,
                        target_id=row.id,
                        observed_at=t.time,
                        lat=t.lat,
                        lon=t.lon,
                        hae=t.hae,
                        ce=t.ce,
                        confidence=0.5,
                        source=f"sensor-{i}",
                        classification=None,
                        created_at=datetime.now(tz=UTC),
                    ),
                )

        select_count = 0

        def count_selects(
            conn: Any,
            cursor: Any,
            statement: str,
            parameters: Any,
            context: Any,
            executemany: bool,
        ) -> None:
            nonlocal select_count
            if statement.lstrip().upper().startswith("SELECT"):
                select_count += 1

        event.listen(engine, "before_cursor_execute", count_selects)
        try:
            with get_session(engine) as session:
                rows = list_targets_on_board(session, board.id)
        finally:
            event.remove(engine, "before_cursor_execute", count_selects)

        assert len(rows) == target_count
        assert rows[0].custom_fields["confidence_chain"] == [
            {"source": "sensor-0", "confidence": 0.5},
        ]
        assert select_count <= 2

    def test_list_targets_in_column(self, engine: Any, board: Board) -> None:
        with get_session(engine) as session:
            ws = create_workspace(session, name="WS4")
            t1 = Target(**{**_target_kwargs(), "name": "in-find"})
            create_target(session, ws.id, board.id, board.columns[0].id, t1)
            t2 = Target(**{**_target_kwargs(), "name": "in-fix"})
            create_target(session, ws.id, board.id, board.columns[1].id, t2)
        with get_session(engine) as session:
            find_col_targets = list_targets_in_column(session, board.columns[0].id)
            fix_col_targets = list_targets_in_column(session, board.columns[1].id)
        assert {t.name for t in find_col_targets} == {"in-find"}
        assert {t.name for t in fix_col_targets} == {"in-fix"}

    def test_move_increments_version(self, engine: Any, board: Board) -> None:
        target = Target(**_target_kwargs())
        with get_session(engine) as session:
            ws = create_workspace(session, name="WS5")
            create_target(session, ws.id, board.id, board.columns[0].id, target)
        with get_session(engine) as session:
            move_target_to_column(session, target.id, board.columns[1].id)
        with get_session(engine) as session:
            moved = get_target(session, target.id)
        assert moved is not None
        assert moved.version == 2

    def test_move_missing_returns_none(self, engine: Any) -> None:
        from uuid import uuid4

        with get_session(engine) as session:
            assert move_target_to_column(session, uuid4(), uuid4()) is None
