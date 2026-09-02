"""Tests for the UTCDatetime Pydantic annotation (tw-qt6).

The bug was: SQLite stores datetimes as TEXT without timezone, so a
naive datetime came back over the wire as "2026-05-17T14:35:17.686298"
— no Z, no offset. JS Date() parses that as LOCAL time per ECMA spec,
making every observation look 4-5 hours in the future for a US-east
browser and freezing the on-card age counter at 0:00. UTCDatetime is
a Pydantic annotated type with a PlainSerializer that emits ISO with
an explicit Z suffix so JS Date() parses correctly.

Backfill TDD step 4. Mutation-tested below.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from pydantic import BaseModel

from target_workspace.utc_datetime import UTCDatetime, _iso_utc


class _Carrier(BaseModel):
    t: UTCDatetime
    maybe_t: UTCDatetime | None = None


def test_iso_utc_serializes_naive_as_utc_with_z_suffix() -> None:
    """A naive datetime is assumed to be UTC (we never write any other
    kind into the DB) and emitted with `Z` so JS Date() parses it
    correctly. The Z suffix is the contract."""
    naive = datetime(2026, 5, 17, 14, 35, 17)
    assert _iso_utc(naive) == "2026-05-17T14:35:17Z"


def test_iso_utc_preserves_aware_datetime_as_utc() -> None:
    """A tz-aware datetime gets normalized to UTC + Z, regardless of
    its source offset. EST input → UTC output."""
    est = timezone(timedelta(hours=-5))
    aware = datetime(2026, 5, 17, 9, 35, 17, tzinfo=est)
    assert _iso_utc(aware) == "2026-05-17T14:35:17Z"


def test_iso_utc_handles_none() -> None:
    assert _iso_utc(None) is None


def test_pydantic_model_dump_json_emits_z_for_naive() -> None:
    """End-to-end: Pydantic's model_dump_json on a UTCDatetime field
    produces a Z-suffixed string. This is the wire contract that JS
    Date() depends on."""
    naive = datetime(2026, 5, 17, 14, 35, 17, 686298)
    m = _Carrier(t=naive)
    payload = m.model_dump_json()
    assert '"t":"2026-05-17T14:35:17.686298Z"' in payload
    # And no naive form anywhere.
    assert '"2026-05-17T14:35:17.686298"' not in payload.replace(
        '"2026-05-17T14:35:17.686298Z"',
        "",
    )


def test_optional_utc_datetime_serializes_none_correctly() -> None:
    m = _Carrier(t=datetime(2026, 5, 17, tzinfo=UTC), maybe_t=None)
    payload = m.model_dump_json()
    assert '"maybe_t":null' in payload


def test_utc_datetime_round_trips_through_json() -> None:
    """JSON output must parse back into an equivalent Pydantic model
    — no information loss, naive in == aware UTC out."""
    naive = datetime(2026, 5, 17, 14, 35, 17, 686298)
    m1 = _Carrier(t=naive)
    payload = m1.model_dump_json()
    m2 = _Carrier.model_validate_json(payload)
    # Re-serializing should be idempotent.
    assert m2.model_dump_json() == payload


def test_microseconds_preserved_through_serializer() -> None:
    """Don't truncate microseconds — the wire format mirrors what the
    DB stores and the client's parseIso depends on lossless round-trip
    for ordering / dedupe correctness."""
    naive = datetime(2026, 5, 17, 14, 35, 17, 1)
    assert _iso_utc(naive) == "2026-05-17T14:35:17.000001Z"
