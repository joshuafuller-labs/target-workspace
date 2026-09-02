"""RFC 7807 Problem Details error responses (tw-33g).

Structured machine-readable error format. Same shape for every error
across the API.

Spec: https://datatracker.ietf.org/doc/html/rfc7807
  {
    "type":   URI reference identifying the problem,
    "title":  Short human-readable summary,
    "status": HTTP status code,
    "detail": Human-readable explanation,
    "instance": URI reference identifying THIS occurrence (optional)
  }
Content-Type: application/problem+json

Assumption documented in tw-33g:
  - Only HTTPException-shaped errors are reformatted. Pydantic validation
    422s are NOT reformatted (FastAPI's default RequestValidationError
    shape is preserved for clients that already understand it).
  - type URI uses the relative form '/v1/problems/<code>' which any
    deployment can re-base to a stable docs URL via reverse-proxy
    rewrite.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.fast]


def test_401_returns_problem_details_format(client: TestClient) -> None:
    r = client.get("/v1/boards")
    assert r.status_code == 401
    assert r.headers.get("content-type", "").startswith(
        "application/problem+json",
    ), r.headers
    body = r.json()
    assert body["status"] == 401
    assert body["title"] == "Unauthorized"
    assert "detail" in body
    assert body["type"].endswith("/v1/problems/unauthorized")


def test_404_returns_problem_details_format(client: TestClient) -> None:
    client.post(
        "/v1/auth/login",
        json={"email": "admin@example.com", "password": "test-pw"},
    )
    r = client.get("/v1/boards/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404
    assert r.headers.get("content-type", "").startswith(
        "application/problem+json",
    )
    body = r.json()
    assert body["status"] == 404
    assert body["title"] == "Not Found"


def test_successful_responses_unaffected(client: TestClient) -> None:
    """Sanity: success paths keep their JSON content type."""
    r = client.post(
        "/v1/auth/login",
        json={"email": "admin@example.com", "password": "test-pw"},
    )
    assert r.status_code == 200
    assert "application/problem+json" not in r.headers.get("content-type", "")
