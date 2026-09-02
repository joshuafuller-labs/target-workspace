"""POST /v1/capture — mobile-friendly target capture (tw-bux).

Per foundation §15 + ADR 0012: an architectural enabler for the mobile
MVP that rides in desktop MVP. The endpoint accepts a minimal multipart
payload (title + GPS + optional photo) and creates a target via the
existing workflow path so audit + realtime + RBAC all work uniformly.

Assumption documented in tw-bux:
  - Photo storage at MVP: write to ${TW_CAPTURES_DIR or
    $XDG_DATA_HOME/tw/captures}/<target_id>.bin and record the
    absolute path on target.custom_fields['photo_path'].
  - Pre-signed URL pattern (S3 / MinIO) is deferred to v1.1.
  - cot_type defaults to a-u-G (unknown ground) for captures; mobile
    operator can override via form field.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.fast]


def _login(c: TestClient) -> None:
    r = c.post("/v1/auth/login", json={"email": "admin@example.com", "password": "test-pw"})
    assert r.status_code == 200, r.text


def _first_board_column(c: TestClient) -> tuple[str, str]:
    boards = c.get("/v1/boards").json()
    if not boards:
        # Fresh DB; create a minimal board.
        r = c.post(
            "/v1/boards",
            json={
                "name": "Captures",
                "columns": [
                    {"name": "Intake", "order": 0},
                    {"name": "Working", "order": 1},
                ],
            },
        )
        assert r.status_code == 201, r.text
        boards = [r.json()]
    board = boards[0]
    return board["id"], board["columns"][0]["id"]


def test_capture_without_photo_creates_target(client: TestClient) -> None:
    _login(client)
    board_id, column_id = _first_board_column(client)

    r = client.post(
        "/v1/capture",
        data={
            "title": "Captured Subject",
            "lat": "35.6",
            "lon": "-82.5",
            "board_id": board_id,
            "column_id": column_id,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "Captured Subject"
    assert body["lat"] == 35.6
    assert body["lon"] == -82.5


def test_capture_with_photo_stores_file_and_records_path(client: TestClient) -> None:
    _login(client)
    board_id, column_id = _first_board_column(client)

    photo_bytes = b"\x89PNG\r\n\x1a\n" + b"fake-png-payload" * 100

    r = client.post(
        "/v1/capture",
        data={
            "title": "Photo Subject",
            "lat": "35.6",
            "lon": "-82.5",
            "board_id": board_id,
            "column_id": column_id,
        },
        files={"photo": ("subject.png", io.BytesIO(photo_bytes), "image/png")},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    photo_path = (body.get("custom_fields") or {}).get("photo_path")
    assert photo_path, f"expected custom_fields.photo_path, got {body}"
    assert Path(photo_path).exists(), f"file not written at {photo_path}"
    assert Path(photo_path).read_bytes() == photo_bytes


def test_capture_missing_required_fields_returns_422(client: TestClient) -> None:
    _login(client)
    r = client.post("/v1/capture", data={"title": "Missing GPS"})
    assert r.status_code == 422


def test_capture_requires_auth(client: TestClient) -> None:
    # No login
    r = client.post(
        "/v1/capture",
        data={
            "title": "Anon",
            "lat": "0",
            "lon": "0",
            "board_id": "00000000-0000-0000-0000-000000000000",
            "column_id": "00000000-0000-0000-0000-000000000000",
        },
    )
    assert r.status_code == 401
