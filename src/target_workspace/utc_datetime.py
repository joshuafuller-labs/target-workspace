"""UTC-tagged datetime — the only datetime type allowed on the wire.

SQLite stores datetimes as TEXT without timezone (even if we wrote them
with `datetime.now(tz=UTC)`). Without a timezone marker on the JSON
response, JavaScript's `new Date()` parses the string as LOCAL time per
ECMA spec — making every observation look like it happened hours in the
future for any non-UTC browser, which clamps the on-card age counter to
0:00 and breaks the timer. tw-qt6.

Using `UTCDatetime` everywhere in API schemas ensures we always emit
`...Z` so JS Date() parses correctly. We assume naive datetimes are UTC
(we never write anything else).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from pydantic import PlainSerializer


def _iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


UTCDatetime = Annotated[datetime, PlainSerializer(_iso_utc, when_used="json")]
