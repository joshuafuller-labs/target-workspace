"""Regression tests for test-suite speed and flake hygiene."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.fast]


def test_cot_listener_tests_poll_instead_of_fixed_sleep() -> None:
    for path in (
        Path("tests/integration/test_cot_in_listener.py"),
        Path("tests/integration/test_cot_in_lifespan.py"),
    ):
        source = path.read_text()

        assert "asyncio.sleep(0.5)" not in source
        assert "_time.sleep(0.6)" not in source
    assert "time.sleep(" not in Path("tests/integration/test_cot_in_lifespan.py").read_text()
    assert (
        "async def _wait_for_listing"
        not in Path("tests/integration/test_cot_in_listener.py").read_text()
    )
    assert (
        "async def _wait_for_value"
        not in Path("tests/integration/test_cot_in_listener.py").read_text()
    )


def test_tak_publisher_tests_do_not_use_fixed_thread_sleeps() -> None:
    for path in (
        Path("tests/unit/test_tak_server_selfsa.py"),
        Path("tests/unit/test_tak_server_negotiation.py"),
        Path("tests/unit/test_tak_server_enrollment.py"),
    ):
        source = path.read_text()

        assert "time.sleep(" not in source


def test_dwell_metric_tests_do_not_use_fixed_sleeps() -> None:
    source = Path("tests/integration/test_metrics_dwell_computation.py").read_text()

    assert "time.sleep(" not in source


def test_sse_stream_tests_do_not_use_fixed_sleeps() -> None:
    source = Path("tests/integration/test_realtime_sse_stream.py").read_text()

    assert "asyncio.sleep(" not in source


def test_sse_stream_tests_use_shared_test_client_fixture() -> None:
    source = Path("tests/integration/test_realtime_sse_stream.py").read_text()

    assert "NamedTemporaryFile" not in source
    assert "TW_DATABASE_URL" not in source
    assert "reset_settings_cache" not in source


def test_slow_account_lockout_tests_use_template_client_fixture() -> None:
    conftest = Path("tests/conftest.py").read_text()
    source = Path("tests/integration/test_account_lockout.py").read_text()

    assert "def migrated_sqlite_template" in conftest
    assert "copy2(" in conftest
    assert "NamedTemporaryFile" not in source
    assert "TW_DATABASE_URL" not in source
    assert "reset_settings_cache" not in source


def test_geofence_tests_use_shared_template_client_fixture() -> None:
    source = Path("tests/integration/test_geofence.py").read_text()

    assert "NamedTemporaryFile" not in source
    assert "TW_DATABASE_URL" not in source
    assert "reset_settings_cache" not in source
    assert "reset_presence_cache" not in source


def test_user_crud_tests_use_shared_authenticated_client_fixture() -> None:
    source = Path("tests/integration/test_user_crud.py").read_text()

    assert "authenticated_client" in Path("tests/conftest.py").read_text()
    assert "TW_DATABASE_URL" not in source
    assert "TW_ADMIN_PASSWORD" not in source
    assert "reset_settings_cache" not in source


def test_board_crud_tests_use_shared_authenticated_client_fixture() -> None:
    source = Path("tests/integration/test_board_crud.py").read_text()

    assert "TW_DATABASE_URL" not in source
    assert "TW_ADMIN_PASSWORD" not in source
    assert "reset_settings_cache" not in source


def test_api_token_tests_use_shared_template_client_fixture() -> None:
    source = Path("tests/integration/test_api_tokens.py").read_text()

    assert "TW_DATABASE_URL" not in source
    assert "create_engine_for_url" not in source
    assert "reset_settings_cache" not in source


@pytest.mark.parametrize(
    ("path", "label"),
    [
        (Path("tests/integration/test_bulk_target_import.py"), "bulk_target_import"),
        (Path("tests/integration/test_auto_eta.py"), "auto_eta"),
        (Path("tests/integration/test_targets_edge_cases.py"), "targets_edge_cases"),
    ],
)
def test_target_api_edge_tests_use_shared_template_client_fixture(path: Path, label: str) -> None:
    assert label
    source = path.read_text()

    assert "NamedTemporaryFile" not in source
    assert "TW_DATABASE_URL" not in source
    assert "reset_settings_cache" not in source


@pytest.mark.parametrize(
    ("path", "label"),
    [
        (Path("tests/integration/test_ingest_webhook.py"), "ingest_webhook"),
        (Path("tests/integration/test_op_period.py"), "op_period"),
        (Path("tests/integration/test_audit_filters.py"), "audit_filters"),
    ],
)
def test_ops_api_tests_use_shared_template_client_fixture(path: Path, label: str) -> None:
    assert label
    source = path.read_text()

    assert "NamedTemporaryFile" not in source
    assert "TW_DATABASE_URL" not in source
    assert "reset_settings_cache" not in source


@pytest.mark.parametrize(
    ("path", "label"),
    [
        (Path("tests/integration/test_ics214_export.py"), "ics214_export"),
        (Path("tests/integration/test_forms_date_window.py"), "forms_date_window"),
        (Path("tests/integration/test_ics_positions.py"), "ics_positions"),
    ],
)
def test_report_form_tests_use_shared_template_client_fixture(path: Path, label: str) -> None:
    assert label
    source = path.read_text()

    assert "NamedTemporaryFile" not in source
    assert "TW_DATABASE_URL" not in source
    assert "reset_settings_cache" not in source


@pytest.mark.parametrize(
    ("path", "label"),
    [
        (Path("tests/integration/test_realtime_ws.py"), "realtime_ws"),
        (Path("tests/integration/test_rate_limit_login.py"), "rate_limit_login"),
        (Path("tests/integration/test_offline_sync_etag.py"), "offline_sync_etag"),
    ],
)
def test_realtime_auth_sync_tests_use_shared_template_client_fixture(
    path: Path, label: str
) -> None:
    assert label
    source = path.read_text()

    assert "NamedTemporaryFile" not in source
    assert "TW_DATABASE_URL" not in source
    assert "reset_settings_cache" not in source


@pytest.mark.parametrize(
    ("path", "label"),
    [
        (Path("tests/integration/test_column_crud.py"), "column_crud"),
        (Path("tests/integration/test_workspace_groups.py"), "workspace_groups"),
        (Path("tests/integration/test_resource_roster.py"), "resource_roster"),
        (Path("tests/integration/test_approving_roles_hint.py"), "approving_roles_hint"),
    ],
)
def test_crud_workspace_tests_use_shared_template_client_fixture(path: Path, label: str) -> None:
    assert label
    source = path.read_text()

    assert "NamedTemporaryFile" not in source
    assert "TW_DATABASE_URL" not in source
    assert "reset_settings_cache" not in source


@pytest.mark.parametrize(
    ("path", "label"),
    [
        (Path("tests/integration/test_auth_audit.py"), "auth_audit"),
        (Path("tests/integration/test_session_revoke.py"), "session_revoke"),
        (Path("tests/integration/test_user_expires_at.py"), "user_expires_at"),
    ],
)
def test_auth_account_tests_use_shared_template_client_fixture(path: Path, label: str) -> None:
    assert label
    source = path.read_text()

    assert "NamedTemporaryFile" not in source
    assert "TW_DATABASE_URL" not in source
    assert "reset_settings_cache" not in source


@pytest.mark.parametrize(
    ("path", "label"),
    [
        (Path("tests/integration/test_column_reorder.py"), "column_reorder"),
        (Path("tests/integration/test_wip_limit.py"), "wip_limit"),
        (Path("tests/integration/test_target_assignees.py"), "target_assignees"),
        (Path("tests/integration/test_cross_board_links.py"), "cross_board_links"),
        (Path("tests/integration/test_workspace_settings.py"), "workspace_settings"),
    ],
)
def test_board_target_ops_tests_use_shared_template_client_fixture(path: Path, label: str) -> None:
    assert label
    source = path.read_text()

    assert "NamedTemporaryFile" not in source
    assert "TW_DATABASE_URL" not in source
    assert "reset_settings_cache" not in source


@pytest.mark.parametrize(
    ("path", "label"),
    [
        (Path("tests/integration/test_plugin_config_api.py"), "plugin_config_api"),
        (Path("tests/integration/test_publisher_health.py"), "publisher_health"),
        (Path("tests/integration/test_totp_mfa.py"), "totp_mfa"),
        (Path("tests/integration/test_mfa_policy.py"), "mfa_policy"),
    ],
)
def test_security_plugin_tests_use_shared_template_client_fixture(path: Path, label: str) -> None:
    assert label
    source = path.read_text()

    assert "NamedTemporaryFile" not in source
    assert "TW_DATABASE_URL" not in source
    assert "reset_settings_cache" not in source


@pytest.mark.parametrize(
    ("path", "label"),
    [
        (Path("tests/integration/test_signed_audit.py"), "signed_audit"),
        (Path("tests/integration/test_track_correlation.py"), "track_correlation"),
        (Path("tests/integration/test_confidence_fusion.py"), "confidence_fusion"),
    ],
)
def test_provenance_workflow_tests_use_shared_template_client_fixture(
    path: Path, label: str
) -> None:
    assert label
    source = path.read_text()

    assert "NamedTemporaryFile" not in source
    assert "TW_DATABASE_URL" not in source
    assert "reset_settings_cache" not in source


@pytest.mark.parametrize(
    ("path", "label"),
    [
        (Path("tests/integration/test_password_reset.py"), "password_reset"),
        (Path("tests/integration/test_force_password_change.py"), "force_password_change"),
        (Path("tests/integration/test_suspicious_login.py"), "suspicious_login"),
        (Path("tests/integration/test_invitations.py"), "invitations"),
        (Path("tests/integration/test_rbac.py"), "rbac"),
    ],
)
def test_auth_access_tests_use_shared_template_client_fixture(path: Path, label: str) -> None:
    assert label
    source = path.read_text()

    assert "NamedTemporaryFile" not in source
    assert "TW_DATABASE_URL" not in source
    assert "reset_settings_cache" not in source


@pytest.mark.parametrize(
    ("path", "label"),
    [
        (Path("tests/integration/test_problem_details.py"), "problem_details"),
        (Path("tests/integration/test_cursor_pagination.py"), "cursor_pagination"),
        (Path("tests/integration/test_idempotency_key.py"), "idempotency_key"),
        (Path("tests/integration/test_audit_since_filter.py"), "audit_since_filter"),
    ],
)
def test_api_reliability_tests_use_shared_template_client_fixture(path: Path, label: str) -> None:
    assert label
    source = path.read_text()

    assert "NamedTemporaryFile" not in source
    assert "TW_DATABASE_URL" not in source
    assert "reset_settings_cache" not in source


@pytest.mark.parametrize(
    ("path", "label"),
    [
        (Path("tests/integration/test_board_templates.py"), "board_templates"),
        (Path("tests/integration/test_damage_assessment.py"), "damage_assessment"),
        (Path("tests/integration/test_tak_callsign.py"), "tak_callsign"),
        (Path("tests/integration/test_stationary_alert.py"), "stationary_alert"),
        (Path("tests/integration/test_dwell_metrics.py"), "dwell_metrics"),
    ],
)
def test_operational_feature_tests_use_shared_template_client_fixture(
    path: Path, label: str
) -> None:
    assert label
    source = path.read_text()

    assert "NamedTemporaryFile" not in source
    assert "TW_DATABASE_URL" not in source
    assert "reset_settings_cache" not in source


@pytest.mark.parametrize(
    ("path", "label"),
    [
        (Path("tests/integration/test_workspace_setup.py"), "workspace_setup"),
        (
            Path("tests/integration/test_demo_scenarios_endpoint.py"),
            "demo_scenarios_endpoint",
        ),
        (Path("tests/integration/test_intake_welfare.py"), "intake_welfare"),
        (Path("tests/integration/test_attachment_refs.py"), "attachment_refs"),
    ],
)
def test_workspace_intake_tests_use_shared_template_client_fixture(path: Path, label: str) -> None:
    assert label
    source = path.read_text()

    assert "NamedTemporaryFile" not in source
    assert "TW_DATABASE_URL" not in source
    assert "reset_settings_cache" not in source


@pytest.mark.parametrize(
    ("path", "label"),
    [
        (Path("tests/integration/test_workflow_triggers.py"), "workflow_triggers"),
        (Path("tests/integration/test_sse_events.py"), "sse_events"),
        (Path("tests/integration/test_global_rate_limit.py"), "global_rate_limit"),
    ],
)
def test_runtime_workflow_tests_use_shared_template_client_fixture(path: Path, label: str) -> None:
    assert label
    source = path.read_text()

    assert "NamedTemporaryFile" not in source
    assert "TW_DATABASE_URL" not in source
    assert "reset_settings_cache" not in source


@pytest.mark.parametrize(
    ("path", "label"),
    [
        (Path("tests/integration/test_per_resource_acl.py"), "per_resource_acl"),
        (Path("tests/integration/test_ics_209.py"), "ics_209"),
        (
            Path("tests/integration/test_metrics_dwell_computation.py"),
            "metrics_dwell_computation",
        ),
        (Path("tests/integration/test_cot_out_dispatch.py"), "cot_out_dispatch"),
        (Path("tests/integration/test_trigger_seam.py"), "trigger_seam"),
    ],
)
def test_security_reporting_tests_use_shared_template_client_fixture(
    path: Path, label: str
) -> None:
    assert label
    source = path.read_text()

    assert "NamedTemporaryFile" not in source
    assert "TW_DATABASE_URL" not in source
    assert "reset_settings_cache" not in source


@pytest.mark.parametrize(
    ("path", "label", "allow_raw_temp_sqlite"),
    [
        (Path("tests/integration/test_capture_endpoint.py"), "capture_endpoint", False),
        (Path("tests/integration/test_pli_presence.py"), "pli_presence", False),
        (Path("tests/integration/test_workspace_export.py"), "workspace_export", True),
    ],
)
def test_capture_presence_export_tests_use_shared_template_client_fixture(
    path: Path, label: str, allow_raw_temp_sqlite: bool
) -> None:
    assert label
    source = path.read_text()

    assert "def client(" not in source
    assert "TW_DATABASE_URL" not in source
    assert "reset_settings_cache" not in source
    if not allow_raw_temp_sqlite:
        assert "NamedTemporaryFile" not in source


@pytest.mark.parametrize(
    ("path", "label", "allow_settings_reset"),
    [
        (Path("tests/integration/test_reorder.py"), "reorder", False),
        (Path("tests/integration/test_map_tile_override.py"), "map_tile_override", True),
    ],
)
def test_reorder_map_tests_use_shared_template_client_fixture(
    path: Path, label: str, allow_settings_reset: bool
) -> None:
    assert label
    source = path.read_text()

    assert "def client(" not in source
    assert "NamedTemporaryFile" not in source
    assert "TW_DATABASE_URL" not in source
    assert "create_app(" not in source
    if not allow_settings_reset:
        assert "reset_settings_cache" not in source


def test_pytest_fails_on_unraisable_resource_warnings() -> None:
    config = Path("pyproject.toml").read_text()

    assert "error::ResourceWarning" in config
    assert "error::pytest.PytestUnraisableExceptionWarning" in config
