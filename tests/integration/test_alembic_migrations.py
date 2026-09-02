"""Alembic migration smoke tests.

These tests verify that:
1. The baseline migration applies cleanly to an empty DB.
2. A new column-add migration rolls forward without data loss.
3. Boot-time `alembic upgrade head` runs through `create_app()`.
"""

from __future__ import annotations

import os
from importlib import import_module
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text
from sqlmodel import Session

from target_workspace.db.engine import create_engine_for_url, reset_engine

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_fk_guardrail_cleanup_quotes_reserved_table_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = import_module("migrations.versions.e0f2b6c8a9d1_add_core_foreign_key_guardrails")
    emitted: list[str] = []
    monkeypatch.setattr(migration.op, "execute", emitted.append)

    migration._null_orphans("promotion_policy", "auto_publish_column_id", "column")

    assert 'FROM "column"' in emitted[0]
    assert 'CAST("column"."id" AS TEXT)' in emitted[0]
    assert 'CAST("promotion_policy"."auto_publish_column_id" AS TEXT)' in emitted[0]


def test_fk_guardrail_cleanup_compares_mixed_uuid_storage_as_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = import_module("migrations.versions.e0f2b6c8a9d1_add_core_foreign_key_guardrails")
    emitted: list[str] = []
    monkeypatch.setattr(migration.op, "execute", emitted.append)

    migration._null_orphans("target_board_link", "added_by", "user")

    assert 'CAST("user"."id" AS TEXT)' in emitted[0]
    assert 'CAST("target_board_link"."added_by" AS TEXT)' in emitted[0]


def test_new_uuid_foreign_key_migrations_use_uuid_columns() -> None:
    migration_paths = [
        REPO_ROOT / "migrations/versions/a8f93c4d6e10_signed_audit_peer_identity.py",
        REPO_ROOT / "migrations/versions/b4a9c2d7e8f1_add_audit_chain_head.py",
        REPO_ROOT / "migrations/versions/e6b7c8d9a0f1_add_workflow_nomination.py",
    ]

    for path in migration_paths:
        migration = path.read_text()
        assert "sa.CHAR(32)" not in migration
        assert "sa.Uuid()" in migration


def test_signed_audit_peer_id_char_schema_has_postgres_repair_migration() -> None:
    repair_migration = (
        REPO_ROOT / "migrations/versions/f4b7c9a2d6e1_repair_audit_peer_uuid_columns.py"
    )

    migration = repair_migration.read_text()

    assert "audit_event" in migration
    assert "instance_identity" in migration
    assert "TYPE UUID USING" in migration
    assert "regexp_replace" in migration
    assert "batch_alter_table" in migration


@pytest.mark.parametrize(
    ("migration_path", "columns"),
    [
        (
            "migrations/versions/d7e8a229f0c5_add_workspace_groups.py",
            [
                "id",
                "workspace_id",
                "group_id",
                "user_id",
                "owning_group_id",
            ],
        ),
        (
            "migrations/versions/b2af13c8e76d_add_per_resource_acl.py",
            ["board_id", "user_id", "target_id"],
        ),
        (
            "migrations/versions/c3b8e9d4f1a2_add_target_board_link.py",
            ["target_id", "board_id", "column_id", "added_by"],
        ),
        (
            "migrations/versions/e5fa12b3d9c0_add_api_token.py",
            ["id", "workspace_id", "created_by_user_id"],
        ),
        (
            "migrations/versions/a4c2e88d3f1b_add_password_reset_token.py",
            ["id", "user_id"],
        ),
        (
            "migrations/versions/f1d3a91c6b27_add_invitation_token.py",
            ["id", "workspace_id", "issued_by_user_id", "group_id"],
        ),
        (
            "migrations/versions/b7e2a8c9d106_add_op_period.py",
            ["id", "board_id", "started_by_user_id", "closed_by_user_id"],
        ),
        (
            "migrations/versions/c4f9a18b30e2_add_ics_positions.py",
            [
                "id",
                "workspace_id",
                "position_id",
                "user_id",
                "op_period_id",
                "transferred_from_assignment_id",
                "transferred_by_user_id",
            ],
        ),
        (
            "migrations/versions/f3d9a517cb84_add_resource_roster.py",
            ["id", "workspace_id"],
        ),
        (
            "migrations/versions/b8e57c1f3a92_add_workflow_trigger.py",
            ["id", "board_id", "action_move_to_column_id"],
        ),
    ],
)
def test_guardrailed_uuid_foreign_key_migrations_use_uuid_columns(
    migration_path: str,
    columns: list[str],
) -> None:
    migration = (REPO_ROOT / migration_path).read_text()

    for column in columns:
        assert f'sa.Column("{column}", sa.CHAR(32)' not in migration
        assert f'sa.Column("{column}", sa.Uuid()' in migration


def _run_alembic_upgrade(database_url: str) -> None:
    """Run `alembic upgrade head` in-process — no subprocess shell dep."""
    os.environ["TW_DATABASE_URL"] = database_url
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    cfg.set_main_option("script_location", str(REPO_ROOT / "migrations"))
    command.upgrade(cfg, "head")


def test_baseline_migration_creates_all_tables(tmp_path: Path) -> None:
    """`alembic upgrade head` on an empty DB produces the full schema."""
    db_path = tmp_path / "baseline.db"
    db_url = f"sqlite:///{db_path}"
    _run_alembic_upgrade(db_url)

    engine = create_engine_for_url(db_url)
    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        assert {"workspace", "user", "board", "column", "target", "audit_event"} <= tables
        # alembic_version should exist and contain the head revision id.
        assert "alembic_version" in tables
    finally:
        engine.dispose()


def test_create_app_runs_migrations_at_boot(tmp_path: Path) -> None:
    """`create_app()` against a fresh DB applies all migrations."""
    db_path = tmp_path / "boot.db"
    db_url = f"sqlite:///{db_path}"
    os.environ["TW_DATABASE_URL"] = db_url
    os.environ["TW_DEMO_SCENARIOS"] = ""
    # Reset the cached settings so the test picks up the new URL.
    import target_workspace.api.config as cfg

    cfg._settings = None
    from target_workspace.api.app import create_app

    create_app()

    engine = create_engine_for_url(db_url)
    try:
        inspector = inspect(engine)
        assert "alembic_version" in inspector.get_table_names()
        with Session(engine) as s:
            row = s.exec(  # type: ignore[call-overload]
                text("SELECT version_num FROM alembic_version"),
            ).one()
            assert row[0]  # non-empty revision string
    finally:
        engine.dispose()
        reset_engine()


def test_create_app_settings_database_url_drives_migrations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit app settings must drive Alembic without matching env vars."""
    db_path = tmp_path / "settings-boot.db"
    db_url = f"sqlite:///{db_path}"
    monkeypatch.delenv("TW_DATABASE_URL", raising=False)
    from target_workspace.api.app import create_app
    from target_workspace.api.config import Settings

    create_app(
        settings=Settings(
            env="test",
            database_url=db_url,
            admin_email="admin@example.com",
            admin_password="test-pw",
            session_secret="test-secret-test-secret-test-secret",
            demo_scenarios="",
            bcrypt_rounds=4,
        ),
    )

    engine = create_engine_for_url(db_url)
    try:
        inspector = inspect(engine)
        assert {"alembic_version", "user"} <= set(inspector.get_table_names())
    finally:
        engine.dispose()
        reset_engine()


def test_run_alembic_upgrade_skips_command_when_database_at_head(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "already-head.db"
    db_url = f"sqlite:///{db_path}"
    _run_alembic_upgrade(db_url)

    def unexpected_upgrade(*_: object, **__: object) -> None:
        raise AssertionError("upgrade should not run for an at-head database")

    monkeypatch.setattr(command, "upgrade", unexpected_upgrade)
    from target_workspace.api import app as app_module

    app_module._run_alembic_upgrade(db_url, env="test")


def test_prod_create_app_fails_closed_when_migration_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "prod-migration-failure.db"
    db_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("TW_DATABASE_URL", db_url)
    monkeypatch.setenv("TW_ENV", "prod")
    monkeypatch.setenv("TW_DEMO_SCENARIOS", "")

    import target_workspace.api.config as cfg

    cfg._settings = None

    def boom(*_: object, **__: object) -> None:
        raise RuntimeError("simulated migration failure")

    monkeypatch.setattr(command, "upgrade", boom)
    from target_workspace.api.app import create_app

    with pytest.raises(RuntimeError, match="alembic upgrade failed"):
        create_app()


def test_readyz_degrades_when_database_is_not_at_alembic_head(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_path = tmp_path / "schema-drift.db"
    db_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("TW_DATABASE_URL", db_url)
    monkeypatch.setenv("TW_DEMO_SCENARIOS", "")

    import target_workspace.api.config as cfg

    cfg._settings = None
    from target_workspace.api.app import create_app

    app = create_app()

    engine = create_engine_for_url(db_url)
    try:
        with engine.begin() as conn:
            conn.execute(text("UPDATE alembic_version SET version_num = 'not-head'"))
    finally:
        engine.dispose()

    with TestClient(app) as c:
        r = c.get("/readyz")

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "degraded"
    assert body["details"]["schema"] == "not-at-head"


@pytest.mark.parametrize(
    "column_name",
    ["geometry_quality", "observation_count", "geometry_kind"],
)
def test_baseline_includes_recent_columns(tmp_path: Path, column_name: str) -> None:
    """Ensure the baseline migration captures the columns that were
    historically added ad-hoc — the very ones that triggered the
    'no such column' regressions tw-188 was filed against."""
    db_path = tmp_path / "cols.db"
    db_url = f"sqlite:///{db_path}"
    _run_alembic_upgrade(db_url)

    engine = create_engine_for_url(db_url)
    try:
        inspector = inspect(engine)
        cols = {c["name"] for c in inspector.get_columns("target")}
        assert column_name in cols, (
            f"target.{column_name} missing from baseline migration — "
            f"existing deploys will fail with 'no such column' on this field"
        )
    finally:
        engine.dispose()
