"""End-to-end API tests via FastAPI TestClient against in-memory SQLite.

This is the contract-level test: a real client driving real HTTP through
the real app stack. If these pass, the demo will work.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlmodel import select

pytestmark = [pytest.mark.fast]


@pytest.fixture
def client() -> Iterator[TestClient]:
    # Force a fresh ephemeral SQLite DB per test
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as dbfile:
        db_path = dbfile.name
    db_url = f"sqlite:///{db_path}"

    os.environ["TW_DATABASE_URL"] = db_url
    os.environ["TW_ADMIN_EMAIL"] = "admin@example.com"
    os.environ["TW_ADMIN_PASSWORD"] = "test-pw"
    os.environ["TW_SESSION_SECRET"] = "test-secret-test-secret-test-secret"

    # Late imports — depend on env being set before module-level cache populates
    from target_workspace.api import config as config_module

    config_module.reset_settings_cache()

    from target_workspace.api.app import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c

    os.unlink(db_path)
    for k in ("TW_DATABASE_URL", "TW_ADMIN_EMAIL", "TW_ADMIN_PASSWORD", "TW_SESSION_SECRET"):
        os.environ.pop(k, None)
    config_module.reset_settings_cache()


def _login(client: TestClient) -> None:
    r = client.post("/v1/auth/login", json={"email": "admin@example.com", "password": "test-pw"})
    assert r.status_code == 200, r.text


def test_healthz(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_readyz(client: TestClient) -> None:
    r = client.get("/readyz")
    assert r.status_code == 200


def test_openapi_emitted(client: TestClient) -> None:
    r = client.get("/v1/openapi.json")
    assert r.status_code == 200
    spec = r.json()
    assert spec["info"]["title"] == "Target Workspace"
    paths = spec["paths"]
    assert "/v1/auth/login" in paths
    assert "/v1/boards" in paths
    assert "/v1/targets" in paths


def test_unauthenticated_requests_rejected(client: TestClient) -> None:
    r = client.get("/v1/auth/me")
    assert r.status_code == 401


def test_login_logout_cycle(client: TestClient) -> None:
    r = client.post("/v1/auth/login", json={"email": "admin@example.com", "password": "test-pw"})
    assert r.status_code == 200
    data = r.json()
    assert data["email"] == "admin@example.com"

    r = client.get("/v1/auth/me")
    assert r.status_code == 200

    r = client.post("/v1/auth/logout")
    assert r.status_code == 200


def test_login_bad_password_rejected(client: TestClient) -> None:
    r = client.post("/v1/auth/login", json={"email": "admin@example.com", "password": "wrong"})
    assert r.status_code == 401


def test_admin_bootstrap_accepts_non_email_login_identifier() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as dbfile:
        db_path = dbfile.name
    db_url = f"sqlite:///{db_path}"

    os.environ["TW_DATABASE_URL"] = db_url
    os.environ["TW_ADMIN_EMAIL"] = "incident-commander"
    os.environ["TW_ADMIN_PASSWORD"] = "test-pw"
    os.environ["TW_SESSION_SECRET"] = "test-secret-test-secret-test-secret"

    from target_workspace.api import config as config_module

    config_module.reset_settings_cache()
    from target_workspace.api.app import create_app

    app = create_app()
    try:
        with TestClient(app) as c:
            r = c.post(
                "/v1/auth/login",
                json={"email": "incident-commander", "password": "test-pw"},
            )
            assert r.status_code == 200, r.text
            assert r.json()["email"] == "incident-commander"
    finally:
        os.unlink(db_path)
        for k in (
            "TW_DATABASE_URL",
            "TW_ADMIN_EMAIL",
            "TW_ADMIN_PASSWORD",
            "TW_SESSION_SECRET",
        ):
            os.environ.pop(k, None)
        config_module.reset_settings_cache()


def _create_board(client: TestClient) -> dict[str, Any]:
    _login(client)
    board_body = {
        "name": "F3EAD",
        "columns": [
            {"name": "FIND", "order": 0},
            {"name": "FIX", "order": 1},
            {"name": "FINISH", "order": 2, "requires_approval": True},
        ],
    }
    r = client.post("/v1/boards", json=board_body)
    assert r.status_code == 201, r.text
    body: dict[str, Any] = r.json()
    return body


def test_create_and_get_board(client: TestClient) -> None:
    board = _create_board(client)
    assert board["name"] == "F3EAD"
    assert len(board["columns"]) == 3
    assert [c["name"] for c in board["columns"]] == ["FIND", "FIX", "FINISH"]

    r = client.get(f"/v1/boards/{board['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == board["id"]


def test_list_boards(client: TestClient) -> None:
    _create_board(client)
    r = client.get("/v1/boards")
    assert r.status_code == 200
    boards = r.json()
    assert len(boards) == 1


def _iso_now() -> str:
    return datetime.now(tz=UTC).isoformat()


def test_full_target_lifecycle(client: TestClient) -> None:
    """The demo path: create board, create target, move it across, query it."""
    board = _create_board(client)
    find_col = board["columns"][0]
    fix_col = board["columns"][1]

    # Create target in FIND
    r = client.post(
        "/v1/targets",
        json={
            "board_id": board["id"],
            "column_id": find_col["id"],
            "name": "BISON-01",
            "lat": 33.4484,
            "lon": -112.0740,
            "time": _iso_now(),
            "confidence": 0.87,
            "custom_fields": {"jiptl_priority": 4},
        },
    )
    assert r.status_code == 201, r.text
    target = r.json()
    assert target["name"] == "BISON-01"
    assert target["version"] == 1
    assert target["custom_fields"]["jiptl_priority"] == 4

    # List by board returns 1
    r = client.get(f"/v1/targets?board_id={board['id']}")
    assert r.status_code == 200
    assert len(r.json()) == 1

    # Filter by column
    r = client.get(f"/v1/targets?board_id={board['id']}&column_id={find_col['id']}")
    assert len(r.json()) == 1

    # Move to FIX
    r = client.post(
        f"/v1/targets/{target['id']}/move",
        json={"column_id": fix_col["id"], "justification": "cross-cue confirmed"},
    )
    assert r.status_code == 200, r.text
    moved = r.json()
    assert moved["version"] == 2

    # FIND now empty; FIX has 1
    r = client.get(f"/v1/targets?board_id={board['id']}&column_id={find_col['id']}")
    assert len(r.json()) == 0
    r = client.get(f"/v1/targets?board_id={board['id']}&column_id={fix_col['id']}")
    assert len(r.json()) == 1

    # Audit log shows the transition
    r = client.get(f"/v1/audit?target_id={target['id']}")
    assert r.status_code == 200
    events = r.json()
    assert any(
        e["event_type"] == "transitioned" and e["justification"] == "cross-cue confirmed"
        for e in events
    )


def test_move_preview_does_not_mutate_or_audit(client: TestClient) -> None:
    board = _create_board(client)
    find_col, fix_col, _finish_col = board["columns"]
    r = client.post(
        "/v1/targets",
        json={
            "board_id": board["id"],
            "column_id": find_col["id"],
            "name": "BISON-PREVIEW",
            "lat": 33.4484,
            "lon": -112.0740,
            "time": _iso_now(),
        },
    )
    assert r.status_code == 201, r.text
    target = r.json()

    r = client.post(
        f"/v1/targets/{target['id']}/move/preview",
        json={"column_id": fix_col["id"], "justification": "cross-cue confirmed"},
    )
    assert r.status_code == 200, r.text
    preview = r.json()
    assert preview["verdict"] == "allow"
    assert preview["target_id"] == target["id"]
    assert preview["to_column_id"] == fix_col["id"]

    current = client.get(f"/v1/targets/{target['id']}").json()
    assert current["version"] == 1
    in_find = client.get(f"/v1/targets?board_id={board['id']}&column_id={find_col['id']}").json()
    in_fix = client.get(f"/v1/targets?board_id={board['id']}&column_id={fix_col['id']}").json()
    assert [row["id"] for row in in_find] == [target["id"]]
    assert in_fix == []
    audit = client.get(f"/v1/audit?target_id={target['id']}").json()
    assert not any(event["event_type"] == "transitioned" for event in audit)


def test_finish_column_requires_approving_role(client: TestClient) -> None:
    board = _create_board(client)
    find_col, fix_col, finish_col = board["columns"]
    r = client.post(
        "/v1/targets",
        json={
            "board_id": board["id"],
            "column_id": find_col["id"],
            "name": "PANTHER-09",
            "lat": 33.0,
            "lon": -112.0,
            "time": _iso_now(),
        },
    )
    assert r.status_code == 201
    target = r.json()

    # FIND -> FIX is fine
    r = client.post(f"/v1/targets/{target['id']}/move", json={"column_id": fix_col["id"]})
    assert r.status_code == 200

    # FIX -> FINISH without approving_role: 400
    r = client.post(f"/v1/targets/{target['id']}/move", json={"column_id": finish_col["id"]})
    assert r.status_code == 400

    # FIX -> FINISH with approving_role: 200
    r = client.post(
        f"/v1/targets/{target['id']}/move",
        json={"column_id": finish_col["id"], "approving_role": "supervisor"},
    )
    assert r.status_code == 200


def _create_target_for_nomination(client: TestClient) -> tuple[dict[str, Any], dict[str, Any]]:
    board = _create_board(client)
    find_col = board["columns"][0]
    r = client.post(
        "/v1/targets",
        json={
            "board_id": board["id"],
            "column_id": find_col["id"],
            "name": "BISON-NOMINATION",
            "lat": 33.0,
            "lon": -112.0,
            "time": _iso_now(),
        },
    )
    assert r.status_code == 201, r.text
    return board, r.json()


def _insert_pending_nomination(
    *,
    target_id: str,
    from_column_id: str,
    to_column_id: str,
) -> str:
    from target_workspace.db import create_engine_for_url, get_session
    from target_workspace.db.tables import (
        UserTable,
        WorkflowNominationTable,
    )

    engine = create_engine_for_url(os.environ["TW_DATABASE_URL"])
    try:
        with get_session(engine) as session:
            user = session.exec(
                select(UserTable).where(UserTable.email == "admin@example.com")
            ).one()
            nomination = WorkflowNominationTable(
                workspace_id=user.workspace_id,
                target_id=UUID(target_id),
                from_column_id=UUID(from_column_id),
                to_column_id=UUID(to_column_id),
                proposed_by="policy:presence",
                actor_id=user.id,
                approver_role="supervisor",
                reason="presence arrived",
                evidence_json={"callsign": "BISON-01"},
                created_at=datetime.now(tz=UTC),
            )
            session.add(nomination)
            session.flush()
            return str(nomination.id)
    finally:
        engine.dispose()


def test_approve_nomination_endpoint_moves_target_and_audits(client: TestClient) -> None:
    board, target = _create_target_for_nomination(client)
    find_col, fix_col, _finish_col = board["columns"]
    nomination_id = _insert_pending_nomination(
        target_id=target["id"],
        from_column_id=find_col["id"],
        to_column_id=fix_col["id"],
    )

    r = client.post(
        f"/v1/targets/nominations/{nomination_id}/approve",
        json={"justification": "supervisor confirmed"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["version"] == 2
    in_find = client.get(f"/v1/targets?board_id={board['id']}&column_id={find_col['id']}").json()
    in_fix = client.get(f"/v1/targets?board_id={board['id']}&column_id={fix_col['id']}").json()
    assert in_find == []
    assert [row["id"] for row in in_fix] == [target["id"]]
    audit = client.get(f"/v1/audit?target_id={target['id']}").json()
    assert any(event["event_type"] == "transitioned" for event in audit)
    assert any(
        event["event_type"] == "approved" and event["metadata"]["nomination_id"] == nomination_id
        for event in audit
    )


def test_reject_nomination_endpoint_does_not_move_target(client: TestClient) -> None:
    board, target = _create_target_for_nomination(client)
    find_col, fix_col, _finish_col = board["columns"]
    nomination_id = _insert_pending_nomination(
        target_id=target["id"],
        from_column_id=find_col["id"],
        to_column_id=fix_col["id"],
    )

    r = client.post(
        f"/v1/targets/nominations/{nomination_id}/reject",
        json={"justification": "bad geofence match"},
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"status": "rejected", "nomination_id": nomination_id}
    current = client.get(f"/v1/targets/{target['id']}").json()
    assert current["version"] == 1
    in_find = client.get(f"/v1/targets?board_id={board['id']}&column_id={find_col['id']}").json()
    in_fix = client.get(f"/v1/targets?board_id={board['id']}&column_id={fix_col['id']}").json()
    assert [row["id"] for row in in_find] == [target["id"]]
    assert in_fix == []
    audit = client.get(f"/v1/audit?target_id={target['id']}").json()
    assert any(
        event["event_type"] == "rejected" and event["metadata"]["nomination_id"] == nomination_id
        for event in audit
    )


def test_create_target_rejects_mismatched_column(client: TestClient) -> None:
    board = _create_board(client)
    bogus_column_id = "00000000-0000-0000-0000-000000000000"
    r = client.post(
        "/v1/targets",
        json={
            "board_id": board["id"],
            "column_id": bogus_column_id,
            "name": "X",
            "lat": 0.0,
            "lon": 0.0,
            "time": _iso_now(),
        },
    )
    assert r.status_code == 400


def test_create_target_rejects_unknown_board(client: TestClient) -> None:
    _login(client)
    r = client.post(
        "/v1/targets",
        json={
            "board_id": "00000000-0000-0000-0000-000000000000",
            "column_id": "00000000-0000-0000-0000-000000000000",
            "name": "X",
            "lat": 0.0,
            "lon": 0.0,
            "time": _iso_now(),
        },
    )
    assert r.status_code == 404


def test_get_missing_target_returns_404(client: TestClient) -> None:
    _login(client)
    r = client.get("/v1/targets/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


def _create_target_for_patch(client: TestClient, *, name: str = "PROBE-01") -> dict[str, Any]:
    board = _create_board(client)
    r = client.post(
        "/v1/targets",
        json={
            "board_id": board["id"],
            "column_id": board["columns"][0]["id"],
            "name": name,
            "cot_type": "a-u-A",
            "lat": 38.5,
            "lon": -105.0,
            "time": _iso_now(),
        },
    )
    assert r.status_code == 201, r.text
    out: dict[str, Any] = r.json()
    return out


def test_patch_target_edits_metadata_fields(client: TestClient) -> None:
    """PATCH /v1/targets/{id} accepts metadata edits and bumps version."""
    target = _create_target_for_patch(client)
    r = client.patch(
        f"/v1/targets/{target['id']}",
        json={
            "cot_type": "a-h-A",
            "remarks": "Affiliation upgraded to HOSTILE per RoE §4.a",
            "source": "Ku-band radar DD-3",
        },
    )
    assert r.status_code == 200, r.text
    updated = r.json()
    assert updated["cot_type"] == "a-h-A"
    assert updated["remarks"].startswith("Affiliation upgraded")
    assert updated["source"] == "Ku-band radar DD-3"
    assert updated["version"] == 2


def test_patch_target_edits_geometry_and_time(client: TestClient) -> None:
    """Intel analyst refining a track: lat/lon/hae/ce and time updateable."""
    target = _create_target_for_patch(client, name="PROBE-GEO")
    r = client.patch(
        f"/v1/targets/{target['id']}",
        json={
            "lat": 38.6,
            "lon": -105.1,
            "hae": 142.0,
            "ce": 8.0,
            "confidence": 0.94,
        },
    )
    assert r.status_code == 200, r.text
    updated = r.json()
    assert updated["lat"] == pytest.approx(38.6)
    assert updated["lon"] == pytest.approx(-105.1)
    assert updated["hae"] == pytest.approx(142.0)
    assert updated["ce"] == pytest.approx(8.0)
    assert updated["confidence"] == pytest.approx(0.94)


def test_patch_target_writes_actor_attributed_audit_event(client: TestClient) -> None:
    """Every PATCH appends an `updated` audit event with actor + diff so the
    audit trail tells you WHO changed WHAT."""
    target = _create_target_for_patch(client, name="PROBE-AUDIT")
    r = client.patch(
        f"/v1/targets/{target['id']}",
        json={"cot_type": "a-h-A", "source": "HUMINT (HCT-7)"},
    )
    assert r.status_code == 200, r.text

    r = client.get(f"/v1/audit?target_id={target['id']}")
    assert r.status_code == 200
    events = r.json()
    updated_events = [e for e in events if e["event_type"] == "updated"]
    assert len(updated_events) == 1
    e = updated_events[0]
    assert e["actor_id"]  # captured the user who edited
    assert "admin@example.com" in (e["justification"] or "")
    diff = e["metadata"]["diff"]
    assert "cot_type" in diff
    assert diff["cot_type"]["from"] == "a-u-A"
    assert diff["cot_type"]["to"] == "a-h-A"
    assert diff["source"]["to"] == "HUMINT (HCT-7)"


def test_patch_target_empty_body_rejected(client: TestClient) -> None:
    target = _create_target_for_patch(client, name="PROBE-EMPTY")
    r = client.patch(f"/v1/targets/{target['id']}", json={})
    assert r.status_code == 400


def test_patch_unknown_target_returns_404(client: TestClient) -> None:
    _login(client)
    r = client.patch(
        "/v1/targets/00000000-0000-0000-0000-000000000000",
        json={"cot_type": "a-h-A"},
    )
    assert r.status_code == 404
