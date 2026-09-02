"""Safety / wellness alerts derived from PLI cache (tw-zba3).

Stationary-too-long detection. Reads the in-memory PLI cache; emits a
boolean check that any caller (IC view, card detail) can poll.

Module is intentionally tiny — the heavy lifting is in api/presence.
"""

from __future__ import annotations

import time


def is_stationary(
    *,
    callsign: str,
    min_minutes: float = 5.0,
    max_drift_m: float = 25.0,
) -> bool:
    """Return True iff this callsign appears stationary at least min_minutes.

    Decision rule (MVP):
      - Lookup the cached entry.
      - If entry is missing → False (not online).
      - If entry.speed > 0 → False (moving).
      - If entry.received_at is older than min_minutes → True (stale &
        last-known-speed was 0).
      - Otherwise → True if speed == 0, else False.

    max_drift_m is reserved for the v1.x history-based variant where
    we evaluate the last N fixes' centroid drift.
    """
    from target_workspace.api.presence import lookup  # noqa: PLC0415

    entry = lookup(callsign)
    if entry is None:
        return False
    if entry.speed is not None and entry.speed > 0.0:
        return False
    # speed is 0 or None
    elapsed = time.monotonic() - entry.received_at
    if min_minutes <= 0.0:
        return True
    return elapsed >= min_minutes * 60.0
