"""Notification trigger seam — audit pipeline fans events out (tw-ngn5).

Enabler. No specific channels at MVP — the seam exists so post-MVP
features (PagerDuty / Slack / SMTP / push) compose on top without
retrofitting the audit pipeline.

Assumption documented in tw-ngn5:
  - Registry is in-memory, populated from entry_points at app boot and
    additionally via register_trigger() for tests / programmatic
    registration.
  - Trigger failures are caught + logged; they MUST NOT propagate into
    the audit pipeline (audit log integrity is non-negotiable).
  - Trigger.on_event() is called synchronously from the audit emission
    path. Implementations that need async I/O are responsible for their
    own task spawning.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.fast]


@dataclass
class _CapturedEvent:
    event_type: str
    actor_id: str | None
    metadata: dict[str, Any]


@dataclass
class _RecordingTrigger:
    """Captures every event whose matches() returns True."""

    name: str = "recording"
    only_event_type: str | None = None
    received: list[_CapturedEvent] = field(default_factory=list)

    def matches(self, event: Any) -> bool:
        if self.only_event_type is None:
            return True
        return event.event_type == self.only_event_type

    def on_event(self, event: Any) -> None:
        self.received.append(
            _CapturedEvent(
                event_type=event.event_type,
                actor_id=str(event.actor_id) if event.actor_id else None,
                metadata=dict(event.metadata or {}),
            )
        )


@dataclass
class _FailingTrigger:
    name: str = "failing"

    def matches(self, event: Any) -> bool:
        return True

    def on_event(self, event: Any) -> None:
        raise RuntimeError("simulated trigger failure")


def test_registered_trigger_receives_matching_audit_events(
    client: TestClient,
) -> None:
    from target_workspace.api.triggers import register_trigger

    recorder = _RecordingTrigger()
    register_trigger(recorder)

    client.post(
        "/v1/auth/login",
        json={"email": "admin@example.com", "password": "test-pw"},
    )

    # The successful login emitted an auth.login.success event.
    assert any(e.event_type == "auth.login.success" for e in recorder.received), (
        f"expected auth.login.success in {recorder.received}"
    )


def test_trigger_with_filter_only_receives_matched_events(
    client: TestClient,
) -> None:
    from target_workspace.api.triggers import register_trigger

    only_failed = _RecordingTrigger(only_event_type="auth.login.failed")
    register_trigger(only_failed)

    # One failure
    client.post(
        "/v1/auth/login",
        json={"email": "ghost@example.com", "password": "x"},
    )
    # One success — should NOT be received
    client.post(
        "/v1/auth/login",
        json={"email": "admin@example.com", "password": "test-pw"},
    )

    types = {e.event_type for e in only_failed.received}
    assert types == {"auth.login.failed"}, f"expected only auth.login.failed, got {types}"


def test_failing_trigger_does_not_break_audit_pipeline(
    client: TestClient,
) -> None:
    """If a trigger raises, audit insertion must still succeed."""
    from target_workspace.api.triggers import register_trigger

    register_trigger(_FailingTrigger())
    # Also register a recorder so we can verify the event was processed
    recorder = _RecordingTrigger()
    register_trigger(recorder)

    r = client.post(
        "/v1/auth/login",
        json={"email": "admin@example.com", "password": "test-pw"},
    )
    assert r.status_code == 200, r.text

    # Login succeeded and audit was written despite the failing trigger
    events = client.get("/v1/audit?limit=10").json()
    assert any(e["event_type"] == "auth.login.success" for e in events)
    # And the recorder still received the event
    assert any(e.event_type == "auth.login.success" for e in recorder.received)


def test_logging_trigger_is_registered_by_default(client: TestClient) -> None:
    """LoggingTrigger reference impl auto-registers on app boot."""
    from target_workspace.api.triggers import (
        LoggingTrigger,
        get_registered_triggers,
    )

    triggers = get_registered_triggers()
    assert any(isinstance(t, LoggingTrigger) for t in triggers), (
        f"expected LoggingTrigger by default, got {[type(t).__name__ for t in triggers]}"
    )
