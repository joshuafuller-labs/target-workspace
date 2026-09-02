"""Persistence layer.

Per ADR 0002, SQLModel (Pydantic + SQLAlchemy) for table mapping. SQLite for
the hobby tier (single-container `docker run`); PostgreSQL+PostGIS for prod.
For MVP we use SQLModel.metadata.create_all on startup; Alembic comes when
we ship a real migration.

Tables in `tables.py` mirror the API schemas in `target_workspace.models`.
Repositories in `repositories.py` convert SQLModel rows <-> Pydantic models.
"""

from target_workspace.db.engine import (
    SessionMaker,
    create_engine_for_url,
    create_tables,
    get_engine,
    get_session,
    init_db,
)

__all__ = [
    "SessionMaker",
    "create_engine_for_url",
    "create_tables",
    "get_engine",
    "get_session",
    "init_db",
]
