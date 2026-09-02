"""Track-correlation integration tests.

Verifies that re-observations of the same physical contact merge into
one Target rather than spawning duplicates, and that the per-target
observation log is queryable. See docs/research/ukraine-fires-targeting.md §1.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.fast]


def _login(client: TestClient) -> None:
    r = client.post(
        "/v1/auth/login",
        json={"email": "admin@example.com", "password": "test-pw"},
    )
    assert r.status_code == 200


def _create_board(client: TestClient) -> dict[str, Any]:
    _login(client)
    r = client.post(
        "/v1/boards",
        json={
            "name": "F3EAD",
            "columns": [
                {"name": "FIND", "order": 0},
                {"name": "FIX", "order": 1},
            ],
        },
    )
    out: dict[str, Any] = r.json()
    return out


def _iso_now() -> str:
    return datetime.now(tz=UTC).isoformat()


def test_two_close_observations_merge_into_one_target(client: TestClient) -> None:
    board = _create_board(client)
    find = board["columns"][0]
    base = {
        "board_id": board["id"],
        "column_id": find["id"],
        "cot_type": "a-h-G-E-V",
        "time": _iso_now(),
    }
    r1 = client.post(
        "/v1/targets",
        json={**base, "name": "BISON-01", "lat": 38.8591, "lon": -105.0419},
    )
    assert r1.status_code == 201
    first_id = r1.json()["id"]
    assert r1.json()["version"] == 1

    # Second observation 50m away — should merge
    r2 = client.post(
        "/v1/targets",
        json={
            **base,
            "name": "BISON-01-redux",
            "lat": 38.8595,
            "lon": -105.0419,
            "time": _iso_now(),
        },
    )
    assert r2.status_code == 201
    assert r2.json()["id"] == first_id, "expected merge, got new target"
    assert r2.json()["version"] == 2, "expected version bump on merge"

    # Listing FIND should still show ONE target
    r = client.get(f"/v1/targets?board_id={board['id']}&column_id={find['id']}")
    assert len(r.json()) == 1


def test_far_observation_creates_new_target(client: TestClient) -> None:
    board = _create_board(client)
    find = board["columns"][0]
    base = {
        "board_id": board["id"],
        "column_id": find["id"],
        "cot_type": "a-h-G-E-V",
        "time": _iso_now(),
    }
    client.post("/v1/targets", json={**base, "name": "X", "lat": 38.85, "lon": -105.04})
    r = client.post(
        "/v1/targets",
        json={**base, "name": "Y", "lat": 38.95, "lon": -105.04, "time": _iso_now()},
    )
    assert r.status_code == 201
    listing = client.get(
        f"/v1/targets?board_id={board['id']}&column_id={find['id']}",
    ).json()
    assert len(listing) == 2


def test_different_affiliation_does_not_merge(client: TestClient) -> None:
    """A hostile observation in the same spot as an unknown should NOT
    fold together — the operator may have refined the affiliation, but
    a SOURCE feed of a different affiliation is a distinct entity."""
    board = _create_board(client)
    find = board["columns"][0]
    client.post(
        "/v1/targets",
        json={
            "board_id": board["id"],
            "column_id": find["id"],
            "cot_type": "a-u-G",
            "name": "UNKNOWN",
            "lat": 38.8591,
            "lon": -105.0419,
            "time": _iso_now(),
        },
    )
    r = client.post(
        "/v1/targets",
        json={
            "board_id": board["id"],
            "column_id": find["id"],
            "cot_type": "a-h-G",
            "name": "HOSTILE",
            "lat": 38.8591,
            "lon": -105.0419,
            "time": _iso_now(),
        },
    )
    assert r.status_code == 201
    listing = client.get(
        f"/v1/targets?board_id={board['id']}&column_id={find['id']}",
    ).json()
    assert len(listing) == 2


def test_observations_endpoint_returns_chain(client: TestClient) -> None:
    board = _create_board(client)
    find = board["columns"][0]
    base = {
        "board_id": board["id"],
        "column_id": find["id"],
        "cot_type": "a-h-G",
        "time": _iso_now(),
    }
    r = client.post(
        "/v1/targets",
        json={**base, "name": "TRACK-01", "lat": 38.85, "lon": -105.04},
    )
    track_id = r.json()["id"]
    client.post(
        "/v1/targets",
        json={
            **base,
            "name": "TRACK-01b",
            "lat": 38.851,
            "lon": -105.04,
            "time": _iso_now(),
        },
    )
    client.post(
        "/v1/targets",
        json={
            **base,
            "name": "TRACK-01c",
            "lat": 38.852,
            "lon": -105.04,
            "time": _iso_now(),
        },
    )

    r = client.get(f"/v1/targets/{track_id}/observations")
    assert r.status_code == 200
    obs = r.json()
    assert len(obs) == 3
    # Should be ordered oldest -> newest
    assert obs[0]["lat"] == pytest.approx(38.85)
    assert obs[2]["lat"] == pytest.approx(38.852)


def test_independent_point_observation_promotes_geometry_quality(client: TestClient) -> None:
    board = _create_board(client)
    find = board["columns"][0]
    base = {
        "board_id": board["id"],
        "column_id": find["id"],
        "cot_type": "a-h-G",
        "time": _iso_now(),
    }
    r1 = client.post(
        "/v1/targets",
        json={
            **base,
            "name": "TRACK-QUALITY",
            "lat": 38.85,
            "lon": -105.04,
            "source": "sensor-alpha",
        },
    )
    assert r1.status_code == 201
    assert r1.json()["geometry_quality"] == "single-source"

    r2 = client.post(
        "/v1/targets",
        json={
            **base,
            "name": "TRACK-QUALITY-2",
            "lat": 38.8501,
            "lon": -105.04,
            "time": _iso_now(),
            "source": "sensor-bravo",
        },
    )
    assert r2.status_code == 201
    assert r2.json()["id"] == r1.json()["id"]
    assert r2.json()["geometry_quality"] == "corroborated"
    assert r2.json()["custom_fields"]["geometry_quality_derivation"] == {
        "method": "independent_observation_sources",
        "source_count": 2,
        "derived": "corroborated",
    }


def test_point_create_geometry_quality_input_does_not_hand_promote(
    client: TestClient,
) -> None:
    board = _create_board(client)
    find = board["columns"][0]
    r = client.post(
        "/v1/targets",
        json={
            "board_id": board["id"],
            "column_id": find["id"],
            "cot_type": "a-h-G",
            "name": "HAND-PROMOTE",
            "lat": 38.85,
            "lon": -105.04,
            "geometry_quality": "confirmed",
            "source": "sensor-alpha",
            "time": _iso_now(),
        },
    )
    assert r.status_code == 201
    assert r.json()["geometry_quality"] == "single-source"
    assert r.json()["custom_fields"]["geometry_quality_derivation"] == {
        "method": "independent_observation_sources",
        "source_count": 1,
        "derived": "single-source",
    }


def test_manual_geometry_quality_override_is_visible_and_distinct(
    client: TestClient,
) -> None:
    board = _create_board(client)
    find = board["columns"][0]
    created = client.post(
        "/v1/targets",
        json={
            "board_id": board["id"],
            "column_id": find["id"],
            "cot_type": "a-h-G",
            "name": "OVERRIDE-QUALITY",
            "lat": 38.85,
            "lon": -105.04,
            "source": "sensor-alpha",
            "time": _iso_now(),
        },
    ).json()

    patched = client.patch(
        f"/v1/targets/{created['id']}",
        json={"geometry_quality": "bearing-only"},
    )
    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert body["geometry_quality"] == "bearing-only"
    assert body["custom_fields"]["geometry_quality_derivation"] == {
        "method": "independent_observation_sources",
        "source_count": 1,
        "derived": "single-source",
    }
    assert body["custom_fields"]["geometry_quality_override"] == {
        "value": "bearing-only",
        "derived": "single-source",
    }

    merged = client.post(
        "/v1/targets",
        json={
            "board_id": board["id"],
            "column_id": find["id"],
            "cot_type": "a-h-G",
            "name": "OVERRIDE-QUALITY-2",
            "lat": 38.8501,
            "lon": -105.04,
            "source": "sensor-bravo",
            "time": _iso_now(),
        },
    )
    assert merged.status_code == 201
    body = merged.json()
    assert body["geometry_quality"] == "bearing-only"
    assert body["custom_fields"]["geometry_quality_derivation"] == {
        "method": "independent_observation_sources",
        "source_count": 2,
        "derived": "corroborated",
    }
    assert body["custom_fields"]["geometry_quality_override"] == {
        "value": "bearing-only",
        "derived": "corroborated",
    }


def test_same_source_observation_does_not_promote_geometry_quality(client: TestClient) -> None:
    board = _create_board(client)
    find = board["columns"][0]
    base = {
        "board_id": board["id"],
        "column_id": find["id"],
        "cot_type": "a-h-G",
        "source": "sensor-alpha",
        "time": _iso_now(),
    }
    r1 = client.post(
        "/v1/targets",
        json={**base, "name": "SAME-SOURCE", "lat": 38.85, "lon": -105.04},
    )
    assert r1.status_code == 201
    r2 = client.post(
        "/v1/targets",
        json={
            **base,
            "name": "SAME-SOURCE-2",
            "lat": 38.8501,
            "lon": -105.04,
            "time": _iso_now(),
        },
    )
    assert r2.status_code == 201
    assert r2.json()["geometry_quality"] == "single-source"
    assert r2.json()["custom_fields"]["geometry_quality_derivation"]["source_count"] == 1


def test_non_point_geometry_quality_does_not_auto_promote(client: TestClient) -> None:
    board = _create_board(client)
    find = board["columns"][0]
    r = client.post(
        "/v1/targets",
        json={
            "board_id": board["id"],
            "column_id": find["id"],
            "cot_type": "a-h-G",
            "name": "AREA-TRACK",
            "lat": 38.85,
            "lon": -105.04,
            "geometry_kind": "polygon",
            "geometry_quality": "bearing-only",
            "polygon_vertices": [
                [38.85, -105.04],
                [38.86, -105.04],
                [38.86, -105.03],
            ],
            "source": "sensor-alpha",
            "time": _iso_now(),
        },
    )
    assert r.status_code == 201
    assert r.json()["geometry_quality"] == "bearing-only"
    assert r.json()["custom_fields"]["geometry_quality_derivation"] == {
        "method": "non_point_fail_closed",
        "derived": "bearing-only",
    }


def test_observation_outside_time_horizon_creates_new_target(client: TestClient) -> None:
    """A target whose last system-update is OLDER than the correlation
    horizon (default 30 min) must NOT match a fresh observation, even
    at identical coordinates + affiliation. Catches the mutation where
    the horizon check is bypassed.

    Recency is `max(time, updated_at)` — to drop a row below the
    horizon both must be aged. The API doesn't expose `updated_at`, so
    we age it via direct DB write.
    """
    from datetime import timedelta as _td
    from uuid import UUID as _UUID

    from sqlmodel import Session

    from target_workspace.db import get_engine
    from target_workspace.db.tables import TargetTable

    board = _create_board(client)
    find = board["columns"][0]
    base = {
        "board_id": board["id"],
        "column_id": find["id"],
        "cot_type": "a-h-G-E-V",
    }
    r1 = client.post(
        "/v1/targets",
        json={**base, "name": "STALE-01", "lat": 38.86, "lon": -105.04, "time": _iso_now()},
    )
    assert r1.status_code == 201
    first_id = r1.json()["id"]

    # Age both `time` and `updated_at` via the ORM. SQLite stores UUIDs
    # without dashes, so a raw SQL UPDATE with the string id would not
    # match — Session.get handles the UUID round-trip correctly.
    stale_dt = datetime.now(tz=UTC) - _td(hours=2)
    with Session(get_engine()) as s:
        row = s.get(TargetTable, _UUID(first_id))
        assert row is not None
        row.time = stale_dt
        row.updated_at = stale_dt
        s.add(row)
        s.commit()

    r2 = client.post(
        "/v1/targets",
        json={**base, "name": "FRESH-01", "lat": 38.86, "lon": -105.04, "time": _iso_now()},
    )
    assert r2.status_code == 201
    assert r2.json()["id"] != first_id, (
        "stale observations beyond the time horizon must not correlate; "
        "expected a new target row, got a merge"
    )
