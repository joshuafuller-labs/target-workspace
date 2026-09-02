"""Board templates + clone-from-board (tw-z9g).

Per decided design (2026-05-17): a 4-tile picker — ICS, SAR, Medical
Triage, F3EAD — plus a 'clone existing board' escape hatch. NOT a
giant template gallery; NOT a blank canvas.

Backend surfaces:
  - GET  /v1/board-templates                 → list of 4 templates
  - POST /v1/board-templates/{id}/instantiate → create a fresh board
                                                 from a template
  - POST /v1/boards/{id}/clone               → clone columns (not targets)
                                                 of an existing board

Assumption documented in tw-z9g:
  - Templates are hard-coded at MVP. Workspace-defined templates are a
    follow-up (post-MVP).
  - Clone copies columns only (with reset wip_limit/color), not targets.
    Cloning a board with cards would conflict with the cross-board
    linking model (target_board_link) — that's a separate UX.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.fast]


def _login(c: TestClient) -> None:
    r = c.post(
        "/v1/auth/login",
        json={"email": "admin@example.com", "password": "test-pw"},
    )
    assert r.status_code == 200, r.text


def test_list_templates_returns_four(client: TestClient) -> None:
    _login(client)
    r = client.get("/v1/board-templates")
    assert r.status_code == 200, r.text
    rows = r.json()
    ids = {t["id"] for t in rows}
    assert ids == {"ics", "sar", "medical-triage", "f3ead"}, ids


def test_instantiate_template_creates_board(client: TestClient) -> None:
    _login(client)
    r = client.post(
        "/v1/board-templates/sar/instantiate",
        json={"name": "Helene SAR Day 3"},
    )
    assert r.status_code == 201, r.text
    board = r.json()
    assert board["name"] == "Helene SAR Day 3"
    assert len(board["columns"]) >= 3  # SAR template has several columns


def test_clone_board_copies_columns_not_targets(client: TestClient) -> None:
    _login(client)
    # Create a board with one target.
    src = client.post(
        "/v1/boards",
        json={
            "name": "Original",
            "columns": [{"name": "X", "order": 0}, {"name": "Y", "order": 1}],
        },
    ).json()
    client.post(
        "/v1/capture",
        data={
            "title": "T1",
            "lat": "0",
            "lon": "0",
            "board_id": src["id"],
            "column_id": src["columns"][0]["id"],
        },
    )

    r = client.post(
        f"/v1/boards/{src['id']}/clone",
        json={"name": "Op-period-2"},
    )
    assert r.status_code == 201, r.text
    cloned = r.json()
    assert cloned["name"] == "Op-period-2"
    assert len(cloned["columns"]) == len(src["columns"])
    # The clone has no targets in any column.
    for _col in cloned["columns"]:
        rows = client.get(f"/v1/boards/{cloned['id']}").json()["columns"]
        for c in rows:
            tgts = client.get(f"/v1/targets?board_id={cloned['id']}&column_id={c['id']}").json()
            assert tgts == [], f"unexpected target in cloned column {c['name']}"


def test_template_endpoints_require_auth(client: TestClient) -> None:
    r = client.get("/v1/board-templates")
    assert r.status_code == 401
