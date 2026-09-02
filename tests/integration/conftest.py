"""Shared test fixtures for the integration suite.

Module-global state — the rate-limit counter (tw-b3bi), the trigger
registry (tw-ngn5), and the email outbox (tw-qj9k) — leaks between
tests. This autouse fixture resets all of them before each test so
ordering doesn't matter.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_global_module_state() -> None:
    """Reset module-globals that survive across tests."""
    try:
        from target_workspace.api.ratelimit import reset_all

        reset_all()
    except Exception:
        pass
    try:
        from target_workspace.api.triggers import clear_triggers

        clear_triggers()
    except Exception:
        pass
    try:
        from target_workspace.api.email import console_outbox

        console_outbox().clear()
    except Exception:
        pass
    try:
        from target_workspace.api.geofence import reset_geofence_state

        reset_geofence_state()
    except Exception:
        pass
    try:
        from target_workspace.api.presence import reset_presence_cache

        reset_presence_cache()
    except Exception:
        pass
    try:
        from target_workspace.api.publisher_health import reset_publisher_health

        reset_publisher_health()
    except Exception:
        pass
