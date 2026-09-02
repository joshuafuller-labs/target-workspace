"""Trigger plugin contract — taps the audit pipeline.

A Trigger receives every audit event whose matches() returns True. The
audit pipeline fans events out to all registered triggers AFTER the
event has been persisted, so trigger failures cannot lose audit log
integrity.

MVP scope (tw-ngn5) is THE SEAM. Specific channels (PagerDuty / Slack /
SMTP / push) are post-MVP features that compose on top.

Discovery: implementations register via the `target_workspace.triggers`
entry-points group OR via api.triggers.register_trigger().
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Trigger(Protocol):
    """A Trigger taps audit events from the pipeline."""

    name: str
    """Stable identifier, e.g. 'pagerduty', 'slack-ops-channel', 'logging'."""

    def matches(self, event: Any) -> bool:
        """Return True iff this trigger wants to receive the event."""
        ...

    def on_event(self, event: Any) -> None:
        """Handle a matching event. May raise — exceptions are caught and
        logged by the pipeline so trigger failures don't corrupt audit log
        integrity. Implementations that need async I/O are responsible for
        their own task spawning."""
        ...
