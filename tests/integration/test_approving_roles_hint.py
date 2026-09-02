"""Approval-role auto-suggest list on columns (tw-cck).

Each column can carry an expected_approving_roles[] list. SPA reads
it from the column and renders a dropdown instead of a free-text
input on the ApprovalPrompt.

Schema:
  ColumnTable.expected_approving_roles: list[str] (JSON, default [])
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


def test_default_columns_have_empty_approving_roles(client: TestClient) -> None:
    _login(client)
    b = client.post(
        "/v1/boards",
        json={"name": "B", "columns": [{"name": "X", "order": 0}]},
    ).json()
    assert b["columns"][0].get("expected_approving_roles", []) == []


def test_can_create_column_with_approving_roles(client: TestClient) -> None:
    _login(client)
    b = client.post(
        "/v1/boards",
        json={
            "name": "B",
            "columns": [
                {
                    "name": "Finish",
                    "order": 0,
                    "requires_approval": True,
                    "expected_approving_roles": ["CDR", "OPS-O", "BN-CDR"],
                },
            ],
        },
    ).json()
    assert b["columns"][0]["expected_approving_roles"] == ["CDR", "OPS-O", "BN-CDR"]


def test_can_patch_approving_roles(client: TestClient) -> None:
    _login(client)
    b = client.post(
        "/v1/boards",
        json={"name": "B", "columns": [{"name": "Finish", "order": 0}]},
    ).json()
    col_id = b["columns"][0]["id"]
    r = client.patch(
        f"/v1/boards/{b['id']}/columns/{col_id}",
        json={"expected_approving_roles": ["S3", "S2"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["expected_approving_roles"] == ["S3", "S2"]
