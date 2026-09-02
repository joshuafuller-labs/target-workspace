"""In-memory Idempotency-Key cache (tw-54t).

Per ADR 0013: mobile clients on flaky networks can safely retry POSTs.
Server caches the (status, body, headers) tuple keyed by
(user_id, path, idempotency_key) for a short TTL.

Single-instance only at MVP. Multi-instance needs Redis (v1.1).
"""

from __future__ import annotations

import time
from collections import OrderedDict
from threading import Lock

# (key) → (expires_at, status, body_bytes, headers)
_cache: OrderedDict[str, tuple[float, int, bytes, dict[str, str]]] = OrderedDict()
_lock = Lock()

TTL_SECONDS = 300  # 5 minutes
MAX_ENTRIES = 10000


def _evict_expired_locked(now: float) -> None:
    """Drop expired entries; runs under lock."""
    to_drop = [k for k, (exp, *_rest) in _cache.items() if exp < now]
    for k in to_drop:
        _cache.pop(k, None)
    # Bound memory in case of pathological key churn.
    while len(_cache) > MAX_ENTRIES:
        _cache.popitem(last=False)


def make_key(*, user_id: str, path: str, idempotency_key: str) -> str:
    return f"{user_id}|{path}|{idempotency_key}"


def get_cached(key: str) -> tuple[int, bytes, dict[str, str]] | None:
    """Return cached response or None."""
    now = time.monotonic()
    with _lock:
        _evict_expired_locked(now)
        entry = _cache.get(key)
        if entry is None:
            return None
        _expires, status_code, body, headers = entry
        return status_code, body, dict(headers)


def store(key: str, status_code: int, body: bytes, headers: dict[str, str]) -> None:
    """Cache a response."""
    expires = time.monotonic() + TTL_SECONDS
    with _lock:
        _cache[key] = (expires, status_code, body, dict(headers))
        _evict_expired_locked(time.monotonic())


def reset_idempotency() -> None:
    """Test helper — flush the cache."""
    with _lock:
        _cache.clear()
