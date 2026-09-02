"""FEMA Preliminary Damage Assessment (PDA) per structure (tw-fgz).

Captures door-to-door damage data on structures. Uses the existing
custom_fields JSON column on target rather than adding a new table —
PDA fields are per-target metadata, not a separate entity.

Endpoint:
  POST /v1/targets/{id}/damage-assessment
  Body: {
    address: str,
    structure_type: str,    # 'residential' | 'commercial' | 'critical-infra' | ...
    occupancy: str,         # 'occupied' | 'vacant' | 'unknown'
    damage_tier: str,       # 'affected' | 'minor' | 'major' | 'destroyed'
    owner_contact: str | None,
    photo_refs: list[str] | None,
    notes: str | None,
  }
  → 200 with the target row, custom_fields.damage_assessment populated.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.fast]


def _login(c: TestClient) -> None:
    r = c.post(
        "/v1/auth/login",
        json={"email": "admin@example.com", "password": "test-pw"},
    )
    assert r.status_code == 200, r.text


def _make_target(c: TestClient) -> dict[str, Any]:
    b = c.post(
        "/v1/boards",
        json={"name": "B", "columns": [{"name": "X", "order": 0}]},
    ).json()
    return c.post(
        "/v1/capture",
        data={
            "title": "142 Oak St",
            "lat": "35.6",
            "lon": "-82.55",
            "board_id": b["id"],
            "column_id": b["columns"][0]["id"],
        },
    ).json()


def test_post_pda_attaches_to_target(client: TestClient) -> None:
    _login(client)
    t = _make_target(client)
    r = client.post(
        f"/v1/targets/{t['id']}/damage-assessment",
        json={
            "address": "142 Oak St, Asheville NC 28801",
            "structure_type": "residential",
            "occupancy": "occupied",
            "damage_tier": "major",
            "owner_contact": "S. Smith / 828-555-0142",
            "photo_refs": ["/captures/abc.bin"],
            "notes": "Roof loss; foundation intact.",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    pda = body["custom_fields"]["damage_assessment"]
    assert pda["address"] == "142 Oak St, Asheville NC 28801"
    assert pda["damage_tier"] == "major"


def test_pda_validates_damage_tier(client: TestClient) -> None:
    _login(client)
    t = _make_target(client)
    r = client.post(
        f"/v1/targets/{t['id']}/damage-assessment",
        json={
            "address": "x",
            "structure_type": "residential",
            "occupancy": "occupied",
            "damage_tier": "totally-borked",
            "owner_contact": None,
            "photo_refs": None,
            "notes": None,
        },
    )
    assert r.status_code == 422, r.text


def test_pda_requires_auth(client: TestClient) -> None:
    r = client.post(
        "/v1/targets/00000000-0000-0000-0000-000000000000/damage-assessment",
        json={
            "address": "x",
            "structure_type": "residential",
            "occupancy": "occupied",
            "damage_tier": "minor",
        },
    )
    assert r.status_code == 401
