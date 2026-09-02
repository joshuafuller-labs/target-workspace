"""DB engine + session lifecycle."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from sqlite3 import Connection as SQLiteConnection
from typing import Any

from sqlalchemy import Engine, event
from sqlmodel import Session, SQLModel, create_engine

# Module-level engine; replaced by init_db() at app boot.
_engine: Engine | None = None
LOG = logging.getLogger(__name__)


SessionMaker = Session


def create_engine_for_url(
    url: str,
    *,
    echo: bool = False,
    worker_count: int = 1,
    connection_warn_threshold: int | None = None,
) -> Engine:
    """Build a SQLAlchemy engine for the given database URL.

    SQLite gets `check_same_thread=False` so FastAPI can hand sessions
    across threads safely. Postgres gets pgbouncer-friendly timeouts and
    a bounded pool sized to worker count.
    """
    connect_args: dict[str, object] = {}
    engine_kwargs: dict[str, object] = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    elif url.startswith("postgresql"):
        safe_worker_count = max(1, worker_count)
        engine_kwargs.update(
            {
                "pool_size": safe_worker_count * 2 + 4,
                "max_overflow": 0,
                "pool_pre_ping": True,
                "pool_recycle": 1800,
            }
        )
        connect_args["options"] = (
            "-c statement_timeout=30000 -c idle_in_transaction_session_timeout=60000"
        )
    engine = create_engine(url, echo=echo, connect_args=connect_args, **engine_kwargs)
    if connection_warn_threshold is not None:
        _install_connection_leak_warning(engine, threshold=connection_warn_threshold)
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _set_sqlite_foreign_keys(
            dbapi_connection: object,
            _: object,
        ) -> None:
            if not isinstance(dbapi_connection, SQLiteConnection):
                return
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def _install_connection_leak_warning(engine: Engine, *, threshold: int) -> None:
    state = {"open": 0}

    @event.listens_for(engine, "checkout")
    def _track_checkout(*_: Any) -> None:
        state["open"] += 1
        if state["open"] > threshold:
            LOG.warning(
                "open DB connections above threshold",
                extra={"open_connections": state["open"], "threshold": threshold},
            )

    @event.listens_for(engine, "checkin")
    def _track_checkin(*_: Any) -> None:
        state["open"] = max(0, state["open"] - 1)


def init_db(
    url: str,
    *,
    echo: bool = False,
    worker_count: int = 1,
    connection_warn_threshold: int | None = None,
) -> Engine:
    """Initialize the module-level engine for application use.

    Call once at app startup. Subsequent get_engine() / get_session() calls
    use the engine created here.
    """
    global _engine  # noqa: PLW0603 — module-level engine is the standard pattern
    if _engine is not None:
        _engine.dispose()
    _engine = create_engine_for_url(
        url,
        echo=echo,
        worker_count=worker_count,
        connection_warn_threshold=connection_warn_threshold,
    )
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        msg = "DB engine not initialized — call init_db(url) at startup."
        raise RuntimeError(msg)
    return _engine


def reset_engine() -> None:
    """Dispose and clear the module-level engine.

    Tests use ephemeral per-test SQLite DBs but the engine here is a
    process-global. Under ``pytest -n auto`` a worker runs many tests in one
    process, so a stale engine (with a connection pool pinned to a previous
    test's now-deleted DB file) can leak into the next test and cause
    order-dependent flakiness. Resetting between tests keeps them isolated.
    """
    global _engine  # noqa: PLW0603 — module-level engine is the standard pattern
    if _engine is not None:
        _engine.dispose()
    _engine = None


def create_tables(engine: Engine | None = None) -> None:
    """Create all tables defined in the SQLModel metadata.

    Used for MVP / SQLite hobby tier. For Postgres production runs use
    Alembic migrations instead (post-MVP).
    """
    # Deferred import is intentional — registers tables in SQLModel.metadata.
    import target_workspace.db.tables  # noqa: F401, PLC0415

    SQLModel.metadata.create_all(engine if engine is not None else get_engine())


@contextmanager
def get_session(engine: Engine | None = None) -> Iterator[Session]:
    """Context-manager session. Commits on success, rolls back on exception.

    `expire_on_commit=False` is set so attributes remain accessible on returned
    rows after the session block exits — important for repository functions
    that return SQLModel instances to callers.
    """
    session = Session(engine if engine is not None else get_engine())
    session.expire_on_commit = False
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
