"""Tests for the HTTP webhook Source adapter (tw-h7x).

The MVP P0 'we can ingest from any AI/CV/OSINT pipeline' story.
External systems POST a per-source JSON body to
POST /v1/ingest/{source_id} with a bearer token; server applies the
configured normalization_map to extract Target fields.

TDD-first — every assertion below was authored before any impl. Each
asserts a behavioural contract, not an implementation detail.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.fast]


@pytest.fixture
def client(authenticated_client: TestClient) -> TestClient:
    return authenticated_client


def _create_board(client: TestClient) -> dict[str, Any]:
    r = client.post(
        "/v1/boards",
        json={
            "name": "T",
            "columns": [{"name": "Find", "order": 0}],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def _provision_webhook_source(
    workspace_id: UUID,
    board_id: UUID,
    column_id: UUID,
    *,
    token_plaintext: str,
    normalization_map: dict[str, Any],
    name: str = "Test Webhook",
) -> UUID:
    """Insert a SourceConfig row via SQLModel — no admin API yet
    (tw-dpe8 covers that follow-up). Returns the source_id."""

    from sqlmodel import Session

    from target_workspace.api.auth import hash_password
    from target_workspace.db import get_engine
    from target_workspace.db.tables import SourceConfigTable

    sid = uuid4()
    with Session(get_engine()) as s:
        s.expire_on_commit = False
        s.add(
            SourceConfigTable(
                id=sid,
                workspace_id=workspace_id,
                name=name,
                plugin_type="http_webhook",
                enabled=True,
                adapter_config={
                    "token_hash": hash_password(token_plaintext),
                    "board_id": str(board_id),
                    "column_id": str(column_id),
                },
                normalization_map=normalization_map,
            ),
        )
        s.commit()
    return sid


def _workspace_id(client: TestClient) -> UUID:
    from sqlmodel import Session, select

    from target_workspace.db import get_engine
    from target_workspace.db.tables import WorkspaceTable

    with Session(get_engine()) as s:
        ws = s.exec(select(WorkspaceTable)).first()
        assert ws is not None
        return ws.id


# ── auth + routing ───────────────────────────────────────────────────


def test_post_to_unknown_source_id_returns_404(client: TestClient) -> None:
    r = client.post(
        f"/v1/ingest/{uuid4()}",
        headers={"Authorization": "Bearer anything"},
        json={"name": "X"},
    )
    assert r.status_code == 404


def test_post_with_no_authorization_header_returns_401(client: TestClient) -> None:
    board = _create_board(client)
    sid = _provision_webhook_source(
        _workspace_id(client),
        UUID(board["id"]),
        UUID(board["columns"][0]["id"]),
        token_plaintext="secret",
        normalization_map={"name": "$.callsign"},
    )
    r = client.post(f"/v1/ingest/{sid}", json={"callsign": "X"})
    assert r.status_code == 401


def test_post_with_wrong_token_returns_401(client: TestClient) -> None:
    board = _create_board(client)
    sid = _provision_webhook_source(
        _workspace_id(client),
        UUID(board["id"]),
        UUID(board["columns"][0]["id"]),
        token_plaintext="correct",
        normalization_map={"name": "$.callsign"},
    )
    r = client.post(
        f"/v1/ingest/{sid}",
        headers={"Authorization": "Bearer wrong"},
        json={"callsign": "X"},
    )
    assert r.status_code == 401


# ── happy path ───────────────────────────────────────────────────────


def test_post_with_valid_token_creates_target(client: TestClient) -> None:
    board = _create_board(client)
    sid = _provision_webhook_source(
        _workspace_id(client),
        UUID(board["id"]),
        UUID(board["columns"][0]["id"]),
        token_plaintext="secret",
        normalization_map={
            "name": "$.callsign",
            "lat": "$.location.lat",
            "lon": "$.location.lng",
            "cot_type": "a-h-G-E-V",  # literal constant (no $. prefix)
            "time": "$.observed_at",
        },
    )
    body = {
        "callsign": "BISON-01",
        "location": {"lat": 33.4484, "lng": -112.0740},
        "observed_at": "2026-05-17T18:00:00Z",
    }
    r = client.post(
        f"/v1/ingest/{sid}",
        headers={"Authorization": "Bearer secret"},
        json=body,
    )
    assert r.status_code == 201, r.text
    target = r.json()
    assert target["name"] == "BISON-01"
    assert target["lat"] == pytest.approx(33.4484)
    assert target["lon"] == pytest.approx(-112.0740)
    assert target["cot_type"] == "a-h-G-E-V"


def test_normalization_with_default_cot_type_when_unmapped(client: TestClient) -> None:
    """If the normalization_map doesn't specify cot_type, the
    Target's default ('a-u-G') applies — the webhook doesn't need to
    insist on a value the publisher might not know."""
    board = _create_board(client)
    sid = _provision_webhook_source(
        _workspace_id(client),
        UUID(board["id"]),
        UUID(board["columns"][0]["id"]),
        token_plaintext="s",
        normalization_map={
            "name": "$.n",
            "lat": "$.lat",
            "lon": "$.lon",
            "time": "$.t",
        },
    )
    r = client.post(
        f"/v1/ingest/{sid}",
        headers={"Authorization": "Bearer s"},
        json={"n": "X", "lat": 0.0, "lon": 0.0, "t": "2026-05-17T18:00:00Z"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["cot_type"] == "a-u-G"


def test_missing_required_field_returns_422(client: TestClient) -> None:
    """Payload lacks the value the normalization_map references → 422
    with a detail pointing at the missing key. We don't silently let
    the request through with garbage lat/lon."""
    board = _create_board(client)
    sid = _provision_webhook_source(
        _workspace_id(client),
        UUID(board["id"]),
        UUID(board["columns"][0]["id"]),
        token_plaintext="s",
        normalization_map={
            "name": "$.callsign",
            "lat": "$.lat",
            "lon": "$.lon",
            "time": "$.t",
        },
    )
    r = client.post(
        f"/v1/ingest/{sid}",
        headers={"Authorization": "Bearer s"},
        json={"callsign": "X", "lat": 0.0},  # missing lon + t
    )
    assert r.status_code == 422, r.text


def test_bulk_post_array_creates_multiple_targets(client: TestClient) -> None:
    """Sending an array of payloads creates one Target per element.
    Lets a batch source (GDELT, BOLO list) drop N events in one POST
    without bouncing N times."""
    board = _create_board(client)
    sid = _provision_webhook_source(
        _workspace_id(client),
        UUID(board["id"]),
        UUID(board["columns"][0]["id"]),
        token_plaintext="s",
        normalization_map={
            "name": "$.n",
            "lat": "$.lat",
            "lon": "$.lon",
            "time": "$.t",
        },
    )
    items = [
        {"n": "A", "lat": 33.0, "lon": -112.0, "t": "2026-05-17T18:00:00Z"},
        {"n": "B", "lat": 34.0, "lon": -113.0, "t": "2026-05-17T18:01:00Z"},
        {"n": "C", "lat": 35.0, "lon": -114.0, "t": "2026-05-17T18:02:00Z"},
    ]
    r = client.post(
        f"/v1/ingest/{sid}",
        headers={"Authorization": "Bearer s"},
        json=items,
    )
    assert r.status_code == 201, r.text
    payload = r.json()
    assert isinstance(payload, list)
    assert len(payload) == 3
    assert {t["name"] for t in payload} == {"A", "B", "C"}


def test_disabled_source_returns_403(client: TestClient) -> None:
    """A source with enabled=False refuses ingest. Lets ops kill a
    misbehaving integration without deleting its config + token."""
    from sqlmodel import Session

    from target_workspace.db import get_engine
    from target_workspace.db.tables import SourceConfigTable

    board = _create_board(client)
    sid = _provision_webhook_source(
        _workspace_id(client),
        UUID(board["id"]),
        UUID(board["columns"][0]["id"]),
        token_plaintext="s",
        normalization_map={"name": "$.n", "lat": "$.lat", "lon": "$.lon", "time": "$.t"},
    )
    # Flip enabled=False
    with Session(get_engine()) as s:
        row = s.get(SourceConfigTable, sid)
        assert row is not None
        row.enabled = False
        s.add(row)
        s.commit()

    r = client.post(
        f"/v1/ingest/{sid}",
        headers={"Authorization": "Bearer s"},
        json={"n": "X", "lat": 0.0, "lon": 0.0, "t": "2026-05-17T18:00:00Z"},
    )
    assert r.status_code == 403


def test_realtime_event_published_on_ingest(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An ingested target fans out to the realtime broker like any
    other create — operators with the board open see new cards
    stream in.

    We monkey-patch Broker.publish to record the calls (the broker's
    subscribe API is an async context manager that doesn't play
    nicely from sync test code; the realtime WS path is covered
    end-to-end by test_realtime_ws.py).
    """
    from target_workspace.api import realtime as rt

    recorded: list[dict[str, Any]] = []
    real_publish = rt.Broker.publish

    def recording_publish(self: rt.Broker, workspace_id: UUID, event: dict[str, Any]) -> None:
        recorded.append(event)
        return real_publish(self, workspace_id, event)

    monkeypatch.setattr(rt.Broker, "publish", recording_publish)

    board = _create_board(client)
    sid = _provision_webhook_source(
        _workspace_id(client),
        UUID(board["id"]),
        UUID(board["columns"][0]["id"]),
        token_plaintext="s",
        normalization_map={"name": "$.n", "lat": "$.lat", "lon": "$.lon", "time": "$.t"},
    )
    r = client.post(
        f"/v1/ingest/{sid}",
        headers={"Authorization": "Bearer s"},
        json={
            "n": "FRESH",
            "lat": 1.0,
            "lon": 2.0,
            "t": datetime.now(tz=UTC).isoformat(),
        },
    )
    assert r.status_code == 201
    created = [e for e in recorded if e.get("type") == "target.created"]
    assert created, f"expected target.created event, got: {recorded}"
    # The event should carry the webhook source's id so downstream
    # consumers can attribute the ingest.
    assert created[-1].get("data", {}).get("source_id") == str(sid)
    assert created[-1].get("data", {}).get("via") == "webhook"
