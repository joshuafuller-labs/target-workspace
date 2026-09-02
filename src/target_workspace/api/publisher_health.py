"""Per-publisher health telemetry (tw-mowp).

In-memory ring of recent publish events keyed by publisher id.
Recorded by the dispatcher (tw-50i5). Read by /v1/publishers/health.

Single-instance MVP; Redis-backed in v1.x for multi-instance ops.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from threading import Lock
from typing import Any

WINDOW_SECONDS = 60.0


@dataclass
class PublisherHealthEntry:
    publisher_id: str
    name: str
    plugin_type: str
    last_publish_at: float | None = None
    last_error_at: float | None = None
    last_error: str | None = None
    successes: deque[float] = field(default_factory=deque)
    failures: deque[float] = field(default_factory=deque)


_entries: dict[str, PublisherHealthEntry] = {}
_lock = Lock()


def _entry_locked(publisher_id: str, name: str, plugin_type: str) -> PublisherHealthEntry:
    entry = _entries.get(publisher_id)
    if entry is None:
        entry = PublisherHealthEntry(
            publisher_id=publisher_id,
            name=name,
            plugin_type=plugin_type,
        )
        _entries[publisher_id] = entry
    # Keep name + plugin_type fresh if they changed.
    entry.name = name
    entry.plugin_type = plugin_type
    return entry


def _trim_locked(entry: PublisherHealthEntry, now: float) -> None:
    cutoff = now - WINDOW_SECONDS
    while entry.successes and entry.successes[0] < cutoff:
        entry.successes.popleft()
    while entry.failures and entry.failures[0] < cutoff:
        entry.failures.popleft()


def record_publish_success(
    *,
    publisher_id: str,
    name: str,
    plugin_type: str,
) -> None:
    now = time.monotonic()
    with _lock:
        e = _entry_locked(publisher_id, name, plugin_type)
        e.last_publish_at = now
        e.successes.append(now)
        _trim_locked(e, now)


def record_publish_failure(
    *,
    publisher_id: str,
    name: str,
    plugin_type: str,
    error: str,
) -> None:
    now = time.monotonic()
    with _lock:
        e = _entry_locked(publisher_id, name, plugin_type)
        e.last_error_at = now
        e.last_error = error
        e.failures.append(now)
        _trim_locked(e, now)


def snapshot() -> list[dict[str, Any]]:
    now = time.monotonic()
    out: list[dict[str, Any]] = []
    with _lock:
        for e in _entries.values():
            _trim_locked(e, now)
            out.append(
                {
                    "publisher_id": e.publisher_id,
                    "name": e.name,
                    "plugin_type": e.plugin_type,
                    "last_publish_at": e.last_publish_at,
                    "last_error_at": e.last_error_at,
                    "last_error": e.last_error,
                    "publish_count_1m": len(e.successes),
                    "error_count_1m": len(e.failures),
                },
            )
    return out


def reset_publisher_health() -> None:
    """Test helper — flush state."""
    with _lock:
        _entries.clear()
