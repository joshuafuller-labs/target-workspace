"""In-memory PLI presence cache (tw-6uz8).

Keyed by callsign. TTL-driven eviction. CoT-in upserts on PLI events;
HTTP + WS clients read. Single-instance MVP (Redis-backed for multi-
instance lives in v1.x).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from threading import Lock
from typing import Any

TTL_SECONDS = 300  # 5 minutes — older than this we treat as offline


@dataclass
class PresenceEntry:
    callsign: str
    lat: float
    lon: float
    hae: float | None
    ce: float | None
    le: float | None
    time_iso: str
    course: float | None
    speed: float | None
    source: str | None
    received_at: float  # time.monotonic() at insert/upsert

    def to_json(self) -> dict[str, Any]:
        return {
            "callsign": self.callsign,
            "lat": self.lat,
            "lon": self.lon,
            "hae": self.hae,
            "ce": self.ce,
            "le": self.le,
            "time": self.time_iso,
            "course": self.course,
            "speed": self.speed,
            "source": self.source,
        }


_cache: dict[str, PresenceEntry] = {}
_lock = Lock()


def _evict_expired_locked(now: float) -> None:
    cutoff = now - TTL_SECONDS
    expired = [k for k, e in _cache.items() if e.received_at < cutoff]
    for k in expired:
        _cache.pop(k, None)


def upsert_pli(
    *,
    callsign: str,
    lat: float,
    lon: float,
    hae: float | None = None,
    ce: float | None = None,
    le: float | None = None,
    time_iso: str,
    course: float | None = None,
    speed: float | None = None,
    source: str | None = None,
) -> PresenceEntry:
    """Upsert a PLI entry. Returns the cached row."""
    now = time.monotonic()
    with _lock:
        _evict_expired_locked(now)
        entry = PresenceEntry(
            callsign=callsign,
            lat=lat,
            lon=lon,
            hae=hae,
            ce=ce,
            le=le,
            time_iso=time_iso,
            course=course,
            speed=speed,
            source=source,
            received_at=now,
        )
        _cache[callsign] = entry
        return entry


def snapshot() -> list[PresenceEntry]:
    """Return all currently-online entries (TTL-pruned)."""
    now = time.monotonic()
    with _lock:
        _evict_expired_locked(now)
        return list(_cache.values())


def lookup(callsign: str) -> PresenceEntry | None:
    """Return one entry or None (post-TTL)."""
    now = time.monotonic()
    with _lock:
        _evict_expired_locked(now)
        return _cache.get(callsign)


def reset_presence_cache() -> None:
    """Test helper — flush the cache."""
    with _lock:
        _cache.clear()


def _cache_for_test() -> dict[str, PresenceEntry]:
    """Test helper — direct dict access for manipulating received_at."""
    return _cache
