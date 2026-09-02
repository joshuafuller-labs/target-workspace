"""In-memory sliding-window rate limiter (tw-b3bi).

MVP scope: a small, dependency-free counter keyed by (bucket, key).
Designed for single-instance deployments. Multi-instance needs Redis
or similar — that's a v1.1 follow-up.

Usage:
    allowed, retry_after = check_and_record(bucket="auth.login", key=ip)
    if not allowed:
        raise HTTPException(429, headers={"Retry-After": str(retry_after)})
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from collections.abc import Iterable
from threading import Lock

# Default limits per bucket. Tunable in v1.1 via settings.
LIMITS: dict[str, tuple[int, float]] = {
    # bucket: (max_events, window_seconds)
    "auth.login.ip": (5, 60.0),
    "auth.forgot_password.ip": (3, 3600.0),
    "auth.forgot_password.email": (3, 86400.0),
    "auth.reset_password.ip": (5, 3600.0),
    "auth.mfa.verify.user": (10, 60.0),
    # tw-bkd: global write rate-limit per IP. Generous default so it
    # only catches misbehaving scrapers, not legitimate operators.
    "http.write.ip": (120, 60.0),
    # tw-858: public welfare-check intake. Conservative — a citizen
    # should never be submitting more than a few per minute.
    "intake.welfare.ip": (10, 60.0),
}

# Pristine snapshot of the defaults. Tests (e.g. test_global_rate_limit) mutate
# LIMITS at runtime to force a low threshold; reset_all() restores this so a
# mutated limit can't leak into later tests sharing the process (xdist worker).
_DEFAULT_LIMITS: dict[str, tuple[int, float]] = dict(LIMITS)

_buckets: dict[tuple[str, str], deque[float]] = defaultdict(deque)
_lock = Lock()


def check_and_record(*, bucket: str, key: str, now: float | None = None) -> tuple[bool, int]:
    """Atomically check and record an event.

    Returns (allowed, retry_after_seconds). When allowed=False the
    caller MUST NOT proceed with the rate-limited operation. The
    record is still added so a back-off attacker doesn't simply
    re-poll past the threshold.
    """
    limit = LIMITS.get(bucket)
    if limit is None:
        # No limit configured for this bucket — allow.
        return True, 0
    max_events, window_seconds = limit
    t = now if now is not None else time.monotonic()
    with _lock:
        q = _buckets[(bucket, key)]
        # Drop timestamps outside the window.
        cutoff = t - window_seconds
        while q and q[0] < cutoff:
            q.popleft()
        if len(q) >= max_events:
            # Compute retry-after as time until oldest in window expires.
            retry = max(1, int(q[0] + window_seconds - t) + 1)
            return False, retry
        q.append(t)
        return True, 0


def reset_all() -> None:
    """Test helper — clear all rate-limit state and restore default limits.

    Also restores LIMITS to its defaults so a test that lowered a threshold
    (e.g. to assert 429) can't leak that limit into later tests on the same
    process under ``pytest -n auto``.
    """
    with _lock:
        _buckets.clear()
        LIMITS.clear()
        LIMITS.update(_DEFAULT_LIMITS)


def reset_bucket(bucket: str, key: str) -> None:
    """Clear a single bucket+key combination."""
    with _lock:
        _buckets.pop((bucket, key), None)


def configured_buckets() -> Iterable[str]:
    """Used by tests / introspection to learn the bucket names."""
    return LIMITS.keys()
