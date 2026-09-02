"""Trigger registry + audit pipeline fan-out (tw-ngn5).

This module wires the Trigger contract (contracts/trigger.py) into the
audit pipeline. After every audit event is persisted, the pipeline calls
fan_out(emitted_event) which dispatches the event to every registered
trigger whose matches() returns True.

Failures are caught + logged so audit integrity is never compromised.

A LoggingTrigger is registered by default as the reference implementation
and a useful debug aid.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from target_workspace.contracts.trigger import Trigger

_log = logging.getLogger(__name__)


# Module-level registry. Populated by register_trigger() at import time
# (for entry-point discovery) and by tests via clear_triggers / register_trigger.
_triggers: list[Trigger] = []


@dataclass
class EmittedAuditEvent:
    """Minimal in-memory record passed to triggers.

    Decoupled from the SQLModel row so triggers can be exercised without
    a DB session. Mirrors the persisted fields plus the signing slots
    populated by tw-16c0.
    """

    id: Any
    workspace_id: Any
    event_type: str
    actor_id: Any | None
    target_id: Any | None
    occurred_at: Any
    metadata: dict[str, Any]
    peer_id: Any | None = None
    signature: str | None = None


@dataclass
class LoggingTrigger:
    """Reference impl: log every event at INFO. Proves the seam works."""

    name: str = "logging"

    def matches(self, event: EmittedAuditEvent) -> bool:
        return True

    def on_event(self, event: EmittedAuditEvent) -> None:
        _log.info(
            "[audit-trigger] type=%s actor=%s target=%s metadata=%s",
            event.event_type,
            event.actor_id,
            event.target_id,
            event.metadata,
        )


def register_trigger(trigger: Trigger) -> None:
    """Register a trigger. Idempotent on identity."""
    if trigger not in _triggers:
        _triggers.append(trigger)


def clear_triggers() -> None:
    """Remove all triggers. Test helper."""
    _triggers.clear()


def get_registered_triggers() -> list[Trigger]:
    """Snapshot of currently registered triggers."""
    return list(_triggers)


def fan_out(event: EmittedAuditEvent) -> None:
    """Dispatch `event` to every matching trigger.

    Trigger failures are caught and logged. The pipeline never raises.
    """
    for trigger in _triggers:
        try:
            if trigger.matches(event):
                trigger.on_event(event)
        except Exception as exc:
            _log.warning(
                "[audit-trigger] trigger=%s failed on event=%s: %s",
                getattr(trigger, "name", type(trigger).__name__),
                event.event_type,
                exc,
            )


def install_default_triggers() -> None:
    """Register the default LoggingTrigger.

    Called from app startup. Idempotent.
    """
    if not any(isinstance(t, LoggingTrigger) for t in _triggers):
        register_trigger(LoggingTrigger())
