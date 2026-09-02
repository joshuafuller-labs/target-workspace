"""Multi-source confidence fusion (tw-a9a).

When correlated observations land on the same target, the aggregate
confidence climbs by the independence rule:
   aggregate = 1 - prod(1 - c_i)
target.custom_fields.confidence_chain is a read-only projection from
TrackObservationTable, not mutable client state.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.fast]


def _login(c: TestClient) -> None:
    r = c.post(
        "/v1/auth/login",
        json={"email": "admin@example.com", "password": "test-pw"},  # pragma: allowlist secret
    )
    assert r.status_code == 200, r.text


def test_fuse_independent_confidences() -> None:
    """Pure-function test of the fusion rule."""
    from target_workspace.api.confidence_fusion import fuse

    assert fuse([]) is None
    assert fuse([0.5]) == pytest.approx(0.5)
    # Two independent 0.5 cues
    assert fuse([0.5, 0.5]) == pytest.approx(0.75)
    # Three 0.5 cues — 1 - 0.5^3 = 0.875
    assert fuse([0.5, 0.5, 0.5]) == pytest.approx(0.875)
    # PANTHER-09: 0.7 + 0.7 + 0.5 → 1 - (0.3 * 0.3 * 0.5) = 0.955
    assert fuse([0.7, 0.7, 0.5]) == pytest.approx(0.955)
    # None values skipped
    assert fuse([0.5, None, 0.5]) == pytest.approx(0.75)


def test_fuse_clamps_inputs() -> None:
    """Out-of-range values are clamped to [0, 1] before fusion."""
    from target_workspace.api.confidence_fusion import fuse

    assert fuse([1.5, 0.5]) == pytest.approx(1.0)
    assert fuse([-0.1, 0.5]) == pytest.approx(0.5)


def test_correlation_merge_writes_chain(client: TestClient) -> None:
    _login(client)
    b = client.post(
        "/v1/boards",
        json={"name": "B", "columns": [{"name": "X", "order": 0}]},
    ).json()

    # First observation — confidence 0.7 from source SAR-1.
    payload = {
        "board_id": b["id"],
        "column_id": b["columns"][0]["id"],
        "name": "PANTHER-09",
        "cot_type": "a-h-G",
        "lat": 35.601,
        "lon": -82.55,
        "time": datetime.now(tz=UTC).isoformat(),
        "confidence": 0.7,
        "source": "SAR-1",
    }
    r1 = client.post("/v1/targets", json=payload)
    assert r1.status_code == 201, r1.text
    t1 = r1.json()

    # Second observation at the SAME lat/lon should correlate-merge.
    payload2 = dict(payload)
    payload2["confidence"] = 0.7
    payload2["source"] = "OSINT-2"
    r2 = client.post("/v1/targets", json=payload2)
    assert r2.status_code == 201, r2.text
    t2 = r2.json()
    assert t2["id"] == t1["id"]  # merged into the same row

    # Third observation — different source, c=0.5.
    payload3 = dict(payload)
    payload3["confidence"] = 0.5
    payload3["source"] = "GDELT-3"
    r3 = client.post("/v1/targets", json=payload3)
    t3 = r3.json()
    assert t3["id"] == t1["id"]

    # Final confidence should be 1 - (0.3 * 0.3 * 0.5) = 0.955 (±)
    assert t3["confidence"] == pytest.approx(0.955, abs=0.01)
    chain = t3["custom_fields"].get("confidence_chain")
    assert isinstance(chain, list)
    assert len(chain) == 3
    sources = sorted([entry["source"] for entry in chain])
    assert sources == ["GDELT-3", "OSINT-2", "SAR-1"]


def test_patch_custom_fields_cannot_alter_fused_confidence_projection(
    client: TestClient,
) -> None:
    _login(client)
    board = client.post(
        "/v1/boards",
        json={"name": "B", "columns": [{"name": "X", "order": 0}]},
    ).json()
    payload = {
        "board_id": board["id"],
        "column_id": board["columns"][0]["id"],
        "name": "TAMPER-01",
        "cot_type": "a-h-G",
        "lat": 35.601,
        "lon": -82.55,
        "time": datetime.now(tz=UTC).isoformat(),
        "confidence": 0.7,
        "source": "SAR-1",
    }
    first = client.post("/v1/targets", json=payload).json()
    payload2 = dict(payload)
    payload2["source"] = "OSINT-2"
    merged = client.post("/v1/targets", json=payload2).json()
    assert merged["id"] == first["id"]
    assert merged["confidence"] == pytest.approx(0.91)

    patched = client.patch(
        f"/v1/targets/{first['id']}",
        json={
            "custom_fields": {
                "confidence_chain": [
                    {"source": "forged", "confidence": 1.0},
                    {"source": "forged-2", "confidence": 1.0},
                ],
                "operator_note": "keep this",
            },
        },
    )
    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert body["confidence"] == pytest.approx(0.91)
    assert body["custom_fields"]["operator_note"] == "keep this"
    chain = body["custom_fields"]["confidence_chain"]
    assert sorted(entry["source"] for entry in chain) == ["OSINT-2", "SAR-1"]
    assert all(entry["source"] != "forged" for entry in chain)
