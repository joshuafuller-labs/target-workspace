from __future__ import annotations

import logging
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import event as sqlalchemy_event

from target_workspace.db import engine as db_engine

pytestmark = [pytest.mark.fast]


class _FakeEngine:
    def __init__(self, url: str) -> None:
        self.url = url
        self.disposed = False

    def dispose(self) -> None:
        self.disposed = True


def test_init_db_disposes_previous_module_engine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[_FakeEngine] = []

    def fake_create_engine_for_url(
        url: str,
        *,
        echo: bool = False,
        worker_count: int = 1,
        connection_warn_threshold: int | None = None,
    ) -> _FakeEngine:
        del echo, worker_count, connection_warn_threshold
        engine = _FakeEngine(url)
        created.append(engine)
        return engine

    db_engine.reset_engine()
    monkeypatch.setattr(db_engine, "create_engine_for_url", fake_create_engine_for_url)

    first = cast(_FakeEngine, db_engine.init_db("sqlite:///one.db"))
    second = cast(_FakeEngine, db_engine.init_db("sqlite:///two.db"))

    assert first.disposed
    assert not second.disposed
    assert cast(_FakeEngine, db_engine.get_engine()) is second


def test_postgres_engine_tunes_pool_from_worker_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_create_engine(url: str, **kwargs: object) -> _FakeEngine:
        calls.append({"url": url, **kwargs})
        return _FakeEngine(url)

    monkeypatch.setattr(db_engine, "create_engine", fake_create_engine)

    engine = db_engine.create_engine_for_url(
        "postgresql+psycopg://tw@db/target_workspace",
        worker_count=3,
    )

    assert isinstance(engine, _FakeEngine)
    call = calls[0]
    assert call["pool_size"] == 10  # workers * 2 + 4
    assert call["max_overflow"] == 0
    assert call["pool_pre_ping"] is True
    assert call["pool_recycle"] == 1800


def test_postgres_engine_sets_statement_timeouts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_create_engine(url: str, **kwargs: object) -> _FakeEngine:
        calls.append({"url": url, **kwargs})
        return _FakeEngine(url)

    monkeypatch.setattr(db_engine, "create_engine", fake_create_engine)

    db_engine.create_engine_for_url("postgresql+psycopg://tw@db/target_workspace")

    connect_args = calls[0]["connect_args"]
    assert isinstance(connect_args, dict)
    assert connect_args["options"] == (
        "-c statement_timeout=30000 -c idle_in_transaction_session_timeout=60000"
    )


def test_sqlite_engine_keeps_thread_args_without_pool_tuning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    def fake_create_engine(url: str, **kwargs: object) -> _FakeEngine:
        calls.append({"url": url, **kwargs})
        return _FakeEngine(url)

    monkeypatch.setattr(db_engine, "create_engine", fake_create_engine)
    monkeypatch.setattr(sqlalchemy_event, "listens_for", lambda *_args, **_kwargs: lambda fn: fn)

    db_engine.create_engine_for_url("sqlite:///tw.db", worker_count=8)

    call = calls[0]
    assert call["connect_args"] == {"check_same_thread": False}
    assert "pool_size" not in call
    assert "max_overflow" not in call


def test_connection_leak_detector_warns_above_threshold(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    warnings: list[tuple[str, dict[str, object] | None]] = []

    def fake_warning(message: str, *, extra: dict[str, object] | None = None) -> None:
        warnings.append((message, extra))

    monkeypatch.setattr(db_engine.LOG, "warning", fake_warning)
    engine = db_engine.create_engine_for_url(
        f"sqlite:///{tmp_path / 'leak.db'}",
        connection_warn_threshold=0,
    )
    try:
        first = engine.connect()
        first.close()
    finally:
        engine.dispose()

    assert warnings == [
        (
            "open DB connections above threshold",
            {"open_connections": 1, "threshold": 0},
        )
    ]


def test_connection_leak_detector_ignores_unconfigured_threshold(
    caplog: pytest.LogCaptureFixture,
) -> None:
    engine = db_engine.create_engine_for_url("sqlite:///:memory:")
    try:
        with caplog.at_level(logging.WARNING):
            first = engine.connect()
            second = engine.connect()
            second.close()
            first.close()
    finally:
        engine.dispose()

    assert not [
        record
        for record in caplog.records
        if record.name == "target_workspace.db.engine"
        and "open DB connections above threshold" in record.getMessage()
    ]
