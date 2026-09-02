"""pytest configuration shared across all test tiers.

Markers are registered in pyproject.toml [tool.pytest.ini_options]. Default
selection runs everything; CI gates use `-m "fast or contract"` for PR
validation and `-m "integration"` separately with testcontainers.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from shutil import copy2

import pytest
from fastapi.testclient import TestClient

from target_workspace import __version__


@pytest.fixture(scope="session")
def workspace_version() -> str:
    """Return the package version (used as a smoke check that imports work)."""
    return __version__


@pytest.fixture(scope="session")
def migrated_sqlite_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Session template DB with Alembic already at head.

    Tests still get isolated DB files; they copy this template instead of
    replaying every migration from scratch for each TestClient boot.
    """
    template = tmp_path_factory.mktemp("db-template") / "template.db"
    from target_workspace.api.app import create_app
    from target_workspace.api.config import Settings, reset_settings_cache
    from target_workspace.db.engine import reset_engine

    settings = Settings(
        env="test",
        database_url=f"sqlite:///{template}",
        admin_email="admin@example.com",
        admin_password="test-pw",
        session_secret="test-secret-test-secret-test-secret",
        demo_scenarios="",
        bcrypt_rounds=4,
    )
    with TestClient(create_app(settings=settings)):
        pass
    reset_settings_cache()
    reset_engine()
    return template


@pytest.fixture
def isolated_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    migrated_sqlite_template: Path,
) -> Callable[[], Iterator[TestClient]]:
    def _make() -> Iterator[TestClient]:
        db = tmp_path / "app.db"
        copy2(migrated_sqlite_template, db)
        monkeypatch.setenv("TW_DATABASE_URL", f"sqlite:///{db}")
        monkeypatch.setenv("TW_ADMIN_EMAIL", "admin@example.com")
        monkeypatch.setenv("TW_ADMIN_PASSWORD", "test-pw")
        monkeypatch.setenv("TW_SESSION_SECRET", "test-secret-test-secret-test-secret")
        monkeypatch.setenv("TW_DEMO_SCENARIOS", "")
        monkeypatch.setenv("TW_ENV", "test")
        monkeypatch.setenv("TW_BCRYPT_ROUNDS", "4")

        from target_workspace.api import config as config_module

        config_module.reset_settings_cache()
        from target_workspace.api.app import create_app

        with TestClient(create_app()) as test_client:
            yield test_client

        config_module.reset_settings_cache()

    return _make


@pytest.fixture
def client(
    isolated_client: Callable[[], Iterator[TestClient]],
) -> Iterator[TestClient]:
    """Default isolated FastAPI client for integration tests.

    Module-local fixtures can still override this when they need custom env,
    base_url, demo scenarios, or app setup. The common path should not open
    temporary SQLite files and mutate process env by hand in every test module.
    """
    yield from isolated_client()


@pytest.fixture
def authenticated_client(
    isolated_client: Callable[[], Iterator[TestClient]],
) -> Iterator[TestClient]:
    """Default isolated FastAPI client with the bootstrap admin logged in."""
    with contextmanager(isolated_client)() as test_client:
        response = test_client.post(
            "/v1/auth/login",
            json={"email": "admin@example.com", "password": "test-pw"},
        )
        assert response.status_code == 200, response.text
        yield test_client


@pytest.fixture(autouse=True)
def _reset_module_singletons() -> Iterator[None]:
    """Isolate tests from in-process module-level state.

    Several modules keep process-global caches (presence, rate-limit buckets,
    idempotency, geofence, publisher health). Under `pytest -n auto`, multiple
    tests share a worker process, so without a reset one test's leftover state
    leaks into the next — causing order-dependent flakiness (e.g. audit/resource
    counts off by one). Reset all of them before every test for a clean slate.
    """
    from target_workspace.api import (
        geofence,
        idempotency,
        presence,
        publisher_health,
        ratelimit,
    )
    from target_workspace.db.engine import reset_engine

    presence.reset_presence_cache()
    idempotency.reset_idempotency()
    ratelimit.reset_all()
    geofence.reset_geofence_state()
    publisher_health.reset_publisher_health()
    # Dispose any engine left pinned to a previous test's ephemeral DB so it
    # can't leak across tests under `pytest -n auto` (each test's client
    # fixture calls init_db() again to set up its own DB).
    reset_engine()
    try:
        yield
    finally:
        reset_engine()
