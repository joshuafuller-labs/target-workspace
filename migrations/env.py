"""Alembic environment — wires SQLModel.metadata + TW_DATABASE_URL.

Reads the URL from the Settings object (same one the API uses) so the
migration run touches the exact DB the app touches. Imports
target_workspace.db.tables so every model registers in
SQLModel.metadata before autogenerate runs.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlmodel import SQLModel

# IMPORTANT: import the tables module directly — NOT through
# target_workspace.api — because `target_workspace.api.__init__` imports
# `app.py`, which calls `create_app()` at module-load time and runs
# SQLModel.metadata.create_all() against the configured DB. That would
# pre-populate the DB before autogenerate could compare against it,
# producing an empty migration. We avoid the whole API package here.
import target_workspace.db.tables  # noqa: F401 — populate SQLModel.metadata

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Prefer a URL supplied by the Alembic caller. Fall back to TW_DATABASE_URL
# for CLI runs without importing the api package, then to a local SQLite DB.
_configured_url = (config.get_main_option("sqlalchemy.url") or "").strip()
_db_url = _configured_url or os.environ.get("TW_DATABASE_URL", "sqlite:///./tw-dev.db")
config.set_main_option("sqlalchemy.url", _db_url)

target_metadata = SQLModel.metadata


def run_migrations_offline() -> None:
    """Emit SQL to stdout — useful for review without touching a DB."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # SQLite needs batch ops for ALTER TABLE.
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against the configured DB."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        is_sqlite = connection.dialect.name == "sqlite"
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # SQLite ALTER TABLE only supports limited ops; batch mode
            # generates a copy-table sequence under the hood. PostgreSQL
            # can use plain ALTERs.
            render_as_batch=is_sqlite,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
