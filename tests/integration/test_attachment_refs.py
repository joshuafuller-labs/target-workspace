"""Attachment refs — URL + content-hash references on targets (tw-b43).

References to imagery, bounding-box overlays, OSINT links, and the
like. Stored on target.custom_fields['attachments'] so no migration
is needed; consumer plugins agree on the shape.

Endpoint:
  POST /v1/targets/{id}/attachments
  Body: {
    kind: 'image' | 'document' | 'osint-link' | 'video' | 'other',
    url: str,                # canonical URL/path
    sha256: str | None,      # content hash (mandatory for image/video; optional for link)
    media_type: str | None,  # e.g. 'image/jpeg'
    caption: str | None,
  }
  → 200 with target row; custom_fields.attachments appended.

DELETE /v1/targets/{id}/attachments/{idx} → 200 with the attachment
removed (idx is zero-based position in the list).
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
            "title": "T",
            "lat": "35.6",
            "lon": "-82.55",
            "board_id": b["id"],
            "column_id": b["columns"][0]["id"],
        },
    ).json()


def test_post_attachment_appends(client: TestClient) -> None:
    _login(client)
    t = _make_target(client)
    r = client.post(
        f"/v1/targets/{t['id']}/attachments",
        json={
            "kind": "image",
            "url": "/captures/abc.jpg",
            "sha256": "a" * 64,
            "media_type": "image/jpeg",
            "caption": "north elevation",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    atts = body["custom_fields"]["attachments"]
    assert len(atts) == 1
    assert atts[0]["url"] == "/captures/abc.jpg"


def test_post_multiple_attachments(client: TestClient) -> None:
    _login(client)
    t = _make_target(client)
    for i in range(3):
        client.post(
            f"/v1/targets/{t['id']}/attachments",
            json={
                "kind": "osint-link",
                "url": f"https://example.com/article-{i}",
                "sha256": None,
                "media_type": None,
                "caption": None,
            },
        )
    body = client.get(f"/v1/targets/{t['id']}").json()
    assert len(body["custom_fields"]["attachments"]) == 3


def test_delete_attachment_by_index(client: TestClient) -> None:
    _login(client)
    t = _make_target(client)
    for i in range(3):
        client.post(
            f"/v1/targets/{t['id']}/attachments",
            json={
                "kind": "osint-link",
                "url": f"https://example.com/{i}",
                "sha256": None,
                "media_type": None,
                "caption": None,
            },
        )
    r = client.delete(f"/v1/targets/{t['id']}/attachments/1")
    assert r.status_code == 200, r.text
    atts = r.json()["custom_fields"]["attachments"]
    assert [a["url"] for a in atts] == [
        "https://example.com/0",
        "https://example.com/2",
    ]


def test_attachment_validates_kind(client: TestClient) -> None:
    _login(client)
    t = _make_target(client)
    r = client.post(
        f"/v1/targets/{t['id']}/attachments",
        json={
            "kind": "totally-bogus",
            "url": "/x",
            "sha256": None,
            "media_type": None,
            "caption": None,
        },
    )
    assert r.status_code == 422


def test_attachment_requires_auth(client: TestClient) -> None:
    r = client.post(
        "/v1/targets/00000000-0000-0000-0000-000000000000/attachments",
        json={"kind": "image", "url": "x", "sha256": None, "media_type": None, "caption": None},
    )
    assert r.status_code == 401
