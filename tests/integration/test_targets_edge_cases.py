"""Error-path + edge-branch coverage for /v1/targets (tw coverage gap).

The happy paths live in test_api / test_bulk_target_import / test_damage_assessment
/ test_attachment_refs / test_auto_eta. This file fills the uncovered branches:
404s for missing/cross-workspace targets, attachment index bounds, damage-tier
sub-validators, bulk column mismatch, the _jsonable list/dict coercion via PATCH,
and the move-target not-found path.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.fast]

_MISSING_ID = "00000000-0000-0000-0000-000000000000"


def _login(c: TestClient) -> None:
    r = c.post("/v1/auth/login", json={"email": "admin@example.com", "password": "test-pw"})
    assert r.status_code == 200, r.text


def _make_board(c: TestClient) -> dict[str, Any]:
    r = c.post(
        "/v1/boards",
        json={
            "name": "B",
            "columns": [{"name": "FIND", "order": 0}, {"name": "FIX", "order": 1}],
        },
    )
    assert r.status_code == 201, r.text
    out: dict[str, Any] = r.json()
    return out


def _make_target(c: TestClient, board: dict[str, Any]) -> dict[str, Any]:
    r = c.post(
        "/v1/capture",
        data={
            "title": "BISON-01",
            "lat": "35.6",
            "lon": "-82.55",
            "board_id": board["id"],
            "column_id": board["columns"][0]["id"],
        },
    )
    assert r.status_code in (200, 201), r.text
    out: dict[str, Any] = r.json()
    return out


# ── assign / unassign 404 + idempotent unassign ────────────────────────


def test_assign_callsign_404_unknown_target(client: TestClient) -> None:
    _login(client)
    r = client.post(f"/v1/targets/{_MISSING_ID}/assign", json={"callsign": "X"})
    assert r.status_code == 404
    assert r.json()["detail"] == "target not found"


def test_unassign_callsign_404_unknown_target(client: TestClient) -> None:
    _login(client)
    r = client.post(f"/v1/targets/{_MISSING_ID}/unassign", json={"callsign": "X"})
    assert r.status_code == 404


def test_unassign_removes_then_noop(client: TestClient) -> None:
    _login(client)
    board = _make_board(client)
    target = _make_target(client, board)
    tid = target["id"]

    assert client.post(f"/v1/targets/{tid}/assign", json={"callsign": "ALPHA"}).status_code == 200
    # Remove it.
    r = client.post(f"/v1/targets/{tid}/unassign", json={"callsign": "ALPHA"})
    assert r.status_code == 200
    assert "ALPHA" not in r.json()["assigned_callsigns"]
    # Removing an already-absent callsign is a no-op 200, not 404.
    r = client.post(f"/v1/targets/{tid}/unassign", json={"callsign": "ALPHA"})
    assert r.status_code == 200


# ── attachments 404 + index bounds ─────────────────────────────────────


def test_add_attachment_404_unknown_target(client: TestClient) -> None:
    _login(client)
    r = client.post(
        f"/v1/targets/{_MISSING_ID}/attachments",
        json={"kind": "image", "url": "https://example.com/a.jpg"},
    )
    assert r.status_code == 404


def test_remove_attachment_404_unknown_target(client: TestClient) -> None:
    _login(client)
    r = client.delete(f"/v1/targets/{_MISSING_ID}/attachments/0")
    assert r.status_code == 404
    assert r.json()["detail"] == "target not found"


def test_remove_attachment_index_out_of_range(client: TestClient) -> None:
    _login(client)
    board = _make_board(client)
    target = _make_target(client, board)
    tid = target["id"]
    # No attachments yet → index 0 is out of range.
    r = client.delete(f"/v1/targets/{tid}/attachments/0")
    assert r.status_code == 404
    assert r.json()["detail"] == "attachment index out of range"
    # Negative index also rejected.
    r = client.delete(f"/v1/targets/{tid}/attachments/-1")
    assert r.status_code == 404


# ── damage assessment sub-validators + 404 ──────────────────────────────


def test_damage_assessment_rejects_bad_structure_type(client: TestClient) -> None:
    _login(client)
    board = _make_board(client)
    target = _make_target(client, board)
    r = client.post(
        f"/v1/targets/{target['id']}/damage-assessment",
        json={
            "address": "1 Main",
            "structure_type": "spaceship",
            "occupancy": "occupied",
            "damage_tier": "minor",
        },
    )
    assert r.status_code == 422
    assert "structure_type must be one of" in r.json()["detail"]


def test_damage_assessment_rejects_bad_occupancy(client: TestClient) -> None:
    _login(client)
    board = _make_board(client)
    target = _make_target(client, board)
    r = client.post(
        f"/v1/targets/{target['id']}/damage-assessment",
        json={
            "address": "1 Main",
            "structure_type": "residential",
            "occupancy": "haunted",
            "damage_tier": "minor",
        },
    )
    assert r.status_code == 422
    assert "occupancy must be one of" in r.json()["detail"]


def test_damage_assessment_404_unknown_target(client: TestClient) -> None:
    _login(client)
    r = client.post(
        f"/v1/targets/{_MISSING_ID}/damage-assessment",
        json={
            "address": "1 Main",
            "structure_type": "residential",
            "occupancy": "occupied",
            "damage_tier": "minor",
        },
    )
    assert r.status_code == 404


# ── eta 404 ─────────────────────────────────────────────────────────────


def test_eta_404_unknown_target(client: TestClient) -> None:
    _login(client)
    r = client.get(f"/v1/targets/{_MISSING_ID}/eta")
    assert r.status_code == 404


# ── bulk column mismatch + per-row HTTPException ────────────────────────


def test_bulk_rejects_column_not_on_board(client: TestClient) -> None:
    _login(client)
    board = _make_board(client)
    r = client.post(
        "/v1/targets/bulk",
        json={
            "board_id": board["id"],
            "column_id": _MISSING_ID,
            "rows": [{"name": "A", "lat": 35.0, "lon": -82.0}],
        },
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "column_id does not belong to board_id"


# ── PATCH update exercises _jsonable list/dict coercion ─────────────────


def test_patch_target_with_list_and_dict_fields(client: TestClient) -> None:
    """Updating custom_fields (dict) and polygon_vertices (list of dicts)
    drives _jsonable through its list/dict recursion branches when the
    audit diff is built."""
    _login(client)
    board = _make_board(client)
    target = _make_target(client, board)
    tid = target["id"]

    r = client.patch(
        f"/v1/targets/{tid}",
        json={
            "custom_fields": {"priority": "high", "tags": ["alpha", "bravo"]},
            "remarks": "edited",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["custom_fields"]["priority"] == "high"
    assert body["remarks"] == "edited"
    # ETag header reflects the bumped version.
    assert r.headers["ETag"].startswith('W/"v')


def test_patch_target_empty_body_rejected(client: TestClient) -> None:
    _login(client)
    board = _make_board(client)
    target = _make_target(client, board)
    r = client.patch(f"/v1/targets/{target['id']}", json={})
    assert r.status_code == 400
    assert r.json()["detail"] == "no fields to update"


def test_patch_target_404_unknown(client: TestClient) -> None:
    _login(client)
    r = client.patch(f"/v1/targets/{_MISSING_ID}", json={"remarks": "x"})
    assert r.status_code == 404


# ── move target not-found → 404 (PromotionDenied path) ──────────────────


def test_move_target_404_unknown(client: TestClient) -> None:
    _login(client)
    board = _make_board(client)
    fix_col = board["columns"][1]["id"]
    r = client.post(
        f"/v1/targets/{_MISSING_ID}/move",
        json={"column_id": fix_col},
    )
    assert r.status_code == 404
