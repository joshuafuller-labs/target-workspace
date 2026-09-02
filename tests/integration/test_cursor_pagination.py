"""Cursor pagination on /v1/audit (tw-13a).

Per ADR 0013. RFC 5988 Link headers carry the next/prev cursors;
cursor is an opaque base64-encoded JSON document — clients should
NOT parse it.

Assumption documented in tw-13a:
  - MVP applies cursor pagination to /v1/audit only (the largest list).
  - Other list endpoints follow the same contract incrementally;
    audit is the canonical example.
  - Filter syntax (?filter=column.state==FINISH) and sort syntax
    (?sort=-time,name) are post-MVP polish — out of scope here.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.fast]


def _login(c: TestClient) -> None:
    """Generate >5 audit events by logging in/out, resetting the rate
    limiter (tw-b3bi 5/min/IP) between attempts so we don't trip 429."""
    from target_workspace.api.ratelimit import reset_all

    for _ in range(8):
        reset_all()
        c.post(
            "/v1/auth/login",
            json={"email": "admin@example.com", "password": "test-pw"},
        )
        c.post("/v1/auth/logout")
    reset_all()
    r = c.post(
        "/v1/auth/login",
        json={"email": "admin@example.com", "password": "test-pw"},
    )
    assert r.status_code == 200


def test_audit_pagination_returns_link_header_with_next(client: TestClient) -> None:
    _login(client)
    r = client.get("/v1/audit?limit=3")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 3
    link = r.headers.get("Link", "")
    assert 'rel="next"' in link, f"expected next link in {link!r}"


def test_following_cursor_yields_distinct_items(client: TestClient) -> None:
    _login(client)
    r1 = client.get("/v1/audit?limit=3")
    page1 = r1.json()
    # Parse the cursor out of the Link header.
    link = r1.headers["Link"]
    # Link: <https://.../v1/audit?limit=3&cursor=XYZ>; rel="next"
    cursor = link.split("cursor=")[1].split(">")[0].split("&")[0]

    r2 = client.get(f"/v1/audit?limit=3&cursor={cursor}")
    assert r2.status_code == 200, r2.text
    page2 = r2.json()
    ids1 = {e["id"] for e in page1}
    ids2 = {e["id"] for e in page2}
    assert ids1.isdisjoint(ids2), f"page2 should be disjoint from page1: overlap={ids1 & ids2}"


def test_last_page_has_no_next_link(client: TestClient) -> None:
    _login(client)
    # Huge limit returns everything; should not include a next link.
    r = client.get("/v1/audit?limit=1000")
    assert r.status_code == 200
    link = r.headers.get("Link", "")
    assert 'rel="next"' not in link


def test_invalid_cursor_returns_422(client: TestClient) -> None:
    _login(client)
    r = client.get("/v1/audit?cursor=not-a-real-cursor!!!")
    assert r.status_code == 422
