"""Database referential integrity guardrails."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from target_workspace.db import create_engine_for_url, create_tables
from target_workspace.db.tables import (
    ApiTokenTable,
    ResourceTable,
    TargetBoardLinkTable,
)
from tests.integration.test_alembic_migrations import _run_alembic_upgrade


def test_sqlite_connections_enforce_foreign_keys(tmp_path: Path) -> None:
    engine = create_engine_for_url(f"sqlite:///{tmp_path / 'fk-pragmas.db'}")
    try:
        with engine.connect() as conn:
            enabled = conn.execute(text("PRAGMA foreign_keys")).scalar_one()
    finally:
        engine.dispose()

    assert enabled == 1


def test_representative_orphan_inserts_fail(tmp_path: Path) -> None:
    engine = create_engine_for_url(f"sqlite:///{tmp_path / 'orphans.db'}")
    try:
        create_tables(engine)

        with Session(engine) as session:
            session.add(
                ResourceTable(
                    workspace_id=uuid4(),
                    callsign="R1",
                    name="Resource",
                    checked_in_at=datetime.now(tz=UTC),
                ),
            )
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()

            session.add(
                ApiTokenTable(
                    workspace_id=uuid4(),
                    created_by_user_id=uuid4(),
                    name="token",
                    token_hash="h",
                    preview="preview",
                    role="viewer",
                    created_at=datetime.now(tz=UTC),
                ),
            )
            with pytest.raises(IntegrityError):
                session.commit()
            session.rollback()

            session.add(
                TargetBoardLinkTable(
                    target_id=uuid4(),
                    board_id=uuid4(),
                    column_id=uuid4(),
                    added_at=datetime.now(tz=UTC),
                ),
            )
            with pytest.raises(IntegrityError):
                session.commit()
    finally:
        engine.dispose()


def test_alembic_schema_has_representative_foreign_keys(tmp_path: Path) -> None:
    db_url = f"sqlite:///{tmp_path / 'migrated-fks.db'}"
    _run_alembic_upgrade(db_url)

    engine = create_engine_for_url(db_url)
    try:
        inspector = inspect(engine)

        def constrained_columns(table_name: str) -> set[str]:
            return {
                column
                for fk in inspector.get_foreign_keys(table_name)
                for column in fk["constrained_columns"]
            }

        assert {"workspace_id", "created_by_user_id"} <= constrained_columns("api_token")
        assert {"target_id", "board_id", "column_id"} <= constrained_columns(
            "target_board_link",
        )
        assert {"workspace_id"} <= constrained_columns("resource")
    finally:
        engine.dispose()
