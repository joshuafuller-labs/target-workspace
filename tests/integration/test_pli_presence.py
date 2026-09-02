"""PLI position cache + WS broadcast (tw-6uz8).

In-memory cache keyed by callsign. CoT-in receives PLI events and
upserts into the cache. Cache entries expire after TTL (default 5min).

Assumption documented in tw-6uz8:
  - In-memory only — single-instance MVP. Redis-backed cache is v1.x.
  - WS event emission ('presence.update') is wired via the existing
    realtime broker; the cache itself is the substrate.
  - PLI ingestion from CoT-in (tw-o13) parses callsigns out of the
    incoming event; the API + cache here can be exercised via a
    direct ingest helper without going through the TCP listener.
"""

from __future__ import annotations

from uuid import UUID

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.fast]


def _login(c: TestClient) -> None:
    r = c.post(
        "/v1/auth/login",
        json={"email": "admin@example.com", "password": "test-pw"},
    )
    assert r.status_code == 200, r.text


def test_empty_presence_returns_empty_list(client: TestClient) -> None:
    _login(client)
    r = client.get("/v1/presence")
    assert r.status_code == 200
    assert r.json() == []


def test_upsert_and_lookup_by_callsign(client: TestClient) -> None:
    from target_workspace.api.presence import upsert_pli

    _login(client)
    upsert_pli(
        callsign="BISON-01",
        lat=35.60,
        lon=-82.55,
        hae=600.0,
        time_iso="2026-05-18T10:00:00Z",
        source="cot-in",
    )

    r = client.get("/v1/presence")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["callsign"] == "BISON-01"

    r = client.get("/v1/presence/BISON-01")
    assert r.status_code == 200
    body = r.json()
    assert body["lat"] == pytest.approx(35.60)
    assert body["lon"] == pytest.approx(-82.55)


def test_lookup_unknown_callsign_returns_404(client: TestClient) -> None:
    _login(client)
    r = client.get("/v1/presence/UNKNOWN-99")
    assert r.status_code == 404


def test_expired_entries_dropped(client: TestClient) -> None:
    """Entries older than the TTL fall off the snapshot."""
    import time as _time

    from target_workspace.api.presence import (
        TTL_SECONDS,
        _cache_for_test,
        upsert_pli,
    )

    _login(client)
    # Manually expire one entry by mutating its 'received_at' to far past.
    upsert_pli(
        callsign="OLD-01",
        lat=0.0,
        lon=0.0,
        hae=None,
        time_iso="2026-05-18T10:00:00Z",
        source="cot-in",
    )
    cache = _cache_for_test()
    entry = cache["OLD-01"]
    entry.received_at = _time.monotonic() - (TTL_SECONDS + 60)

    r = client.get("/v1/presence")
    callsigns = [row["callsign"] for row in r.json()]
    assert "OLD-01" not in callsigns


def test_presence_requires_auth(client: TestClient) -> None:
    r = client.get("/v1/presence")
    assert r.status_code == 401


def test_post_presence_arrival_creates_workflow_nomination(client: TestClient) -> None:
    from sqlmodel import select

    from target_workspace.db import get_engine, get_session
    from target_workspace.db.tables import TargetTable, WorkflowNominationTable

    _login(client)
    board = client.post(
        "/v1/boards",
        json={
            "name": "SAR",
            "columns": [
                {"name": "Assigned", "order": 0},
                {"name": "On-scene", "order": 1},
            ],
        },
    ).json()
    assigned_col = board["columns"][0]["id"]
    on_scene_col = board["columns"][1]["id"]
    target = client.post(
        "/v1/capture",
        data={
            "title": "Rescue 12",
            "lat": "35.60000",
            "lon": "-82.55000",
            "board_id": board["id"],
            "column_id": assigned_col,
        },
    ).json()
    assign = client.post(f"/v1/targets/{target['id']}/assign", json={"callsign": "MEDIC-1"})
    assert assign.status_code == 200, assign.text
    trigger = client.post(
        f"/v1/boards/{board['id']}/workflow-triggers",
        json={
            "trigger": "presence.arrived",
            "condition": "min_assignees:1",
            "action_move_to_column_id": on_scene_col,
            "justification_template": "{callsign} arrived",
        },
    )
    assert trigger.status_code == 200, trigger.text

    r = client.post(
        "/v1/presence",
        json={
            "callsign": "MEDIC-1",
            "lat": 35.60001,
            "lon": -82.55000,
            "time": "2026-06-05T02:00:00Z",
            "source": "test-pli",
        },
    )

    assert r.status_code == 200, r.text
    assert r.json()["workflow_results"][0]["verdict"] == "propose"
    with get_session(get_engine()) as session:
        row = session.get(TargetTable, UUID(target["id"]))
        nomination = session.exec(
            select(WorkflowNominationTable).where(
                WorkflowNominationTable.target_id == UUID(target["id"])
            )
        ).one()
    assert row is not None
    assert row.column_id == UUID(assigned_col)
    assert row.version == 1
    assert nomination.to_column_id == UUID(on_scene_col)
    assert nomination.proposed_by == f"workflow:presence:{trigger.json()['id']}"
    assert nomination.evidence_json["callsign"] == "MEDIC-1"
    assert nomination.evidence_json["geo_attestation"]["source"] == "test-pli"
    audit = client.get(f"/v1/audit?target_id={target['id']}").json()
    nominated = next(event for event in audit if event["event_type"] == "nominated")
    assert nominated["actor_kind"] == "policy_agent"
    assert nominated["actor_ref"] == f"workflow:presence:{trigger.json()['id']}"
    assert nominated["signature_format_version"] == 2
