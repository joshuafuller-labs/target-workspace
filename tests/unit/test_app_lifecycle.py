from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from target_workspace.api import app as app_module
from target_workspace.api.config import Settings

pytestmark = [pytest.mark.fast]


class _FakeEngine:
    def __init__(self) -> None:
        self.disposed = False

    def dispose(self) -> None:
        self.disposed = True


def test_lifespan_shutdown_disposes_app_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = _FakeEngine()
    reset_called = False

    async def fake_start_cot_in_listeners(_engine: object) -> list[Any]:
        return []

    def fake_reset_engine() -> None:
        nonlocal reset_called
        reset_called = True

    monkeypatch.setattr(app_module, "init_db", lambda *_args, **_kwargs: engine)
    monkeypatch.setattr(app_module, "_run_alembic_upgrade", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app_module, "create_tables", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app_module, "_ensure_bootstrap_user", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app_module, "_seed_demo_scenarios", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app_module, "_backfill_legacy_audit_chain", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app_module, "_start_cot_in_listeners", fake_start_cot_in_listeners)
    monkeypatch.setattr(app_module, "reset_engine", fake_reset_engine, raising=False)

    settings = Settings(
        env="test",
        database_url="sqlite:///unused.db",
        admin_password="test-pw",  # pragma: allowlist secret
        session_secret="test-secret-test-secret-test-secret",  # pragma: allowlist secret
    )

    with TestClient(app_module.create_app(settings=settings)):
        assert not engine.disposed

    assert engine.disposed
    assert reset_called
