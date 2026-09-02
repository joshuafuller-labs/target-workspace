"""Admin API for plugin discovery and Source/Publisher config CRUD."""

from __future__ import annotations

from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

pytestmark = [pytest.mark.fast]


def _login_admin(c: TestClient) -> None:
    r = c.post(
        "/v1/auth/login",
        json={"email": "admin@example.com", "password": "test-pw"},  # pragma: allowlist secret
    )
    assert r.status_code == 200, r.text


def _create_viewer(c: TestClient) -> None:
    _login_admin(c)
    r = c.post(
        "/v1/users",
        json={
            "email": "viewer@example.com",
            "display_name": "Viewer",
            "role": "viewer",
            "password": "viewer-pass-123",  # pragma: allowlist secret
        },
    )
    assert r.status_code == 201, r.text
    c.post("/v1/auth/logout")


def test_plugin_discovery_lists_registered_families(client: TestClient) -> None:
    _login_admin(client)

    r = client.get("/v1/plugins")

    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) >= {"sources", "publishers", "effectors"}
    assert {"name": "manual", "kind": "source"} in body["sources"]
    assert {"name": "http_webhook", "kind": "source"} in body["sources"]
    assert {"name": "raw_cot", "kind": "publisher"} in body["publishers"]
    assert {"name": "tak_server", "kind": "publisher"} in body["publishers"]
    assert {"name": "manual_effector", "kind": "effector"} in body["effectors"]


def test_source_crud_test_connection_and_audit(client: TestClient) -> None:
    _login_admin(client)

    r = client.post(
        "/v1/sources",
        json={
            "name": "Webhook",
            "plugin_type": "http_webhook",
            "enabled": True,
            "adapter_config": {"auth": "shared-secret-ref"},
            "normalization_map": {
                "name": "$.callsign",
                "cot_type": "a-f-G-U-C",
                "lat": "$.location.lat",
                "lon": "$.location.lon",
            },
        },
    )
    assert r.status_code == 201, r.text
    created = r.json()
    source_id = created["id"]
    assert created["name"] == "Webhook"

    r = client.get("/v1/sources")
    assert r.status_code == 200, r.text
    assert [row["id"] for row in r.json()] == [source_id]

    r = client.post(
        f"/v1/sources/{source_id}/test",
        json={"payload": {"callsign": "ALPHA-1", "location": {"lat": 30.1, "lon": -97.2}}},
    )
    assert r.status_code == 200, r.text
    assert r.json()["normalized"] == {
        "name": "ALPHA-1",
        "cot_type": "a-f-G-U-C",
        "lat": 30.1,
        "lon": -97.2,
    }

    r = client.patch(f"/v1/sources/{source_id}", json={"name": "Webhook In", "enabled": False})
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Webhook In"
    assert r.json()["enabled"] is False

    r = client.delete(f"/v1/sources/{source_id}")
    assert r.status_code == 204, r.text
    assert client.get("/v1/sources").json() == []

    r = client.get("/v1/audit?event_type=source.created")
    assert r.status_code == 200, r.text
    assert r.json()[0]["metadata"]["source_config_id"] == source_id
    r = client.get("/v1/audit?event_type=source.updated")
    assert r.status_code == 200, r.text
    assert r.json()[0]["metadata"]["source_config_id"] == source_id
    r = client.get("/v1/audit?event_type=source.deleted")
    assert r.status_code == 200, r.text
    assert r.json()[0]["metadata"]["source_config_id"] == source_id


def test_publisher_crud_and_audit(client: TestClient) -> None:
    _login_admin(client)

    column_id = str(UUID("00000000-0000-0000-0000-000000000001"))
    r = client.post(
        "/v1/publishers",
        json={
            "name": "TAK Lab",
            "plugin_type": "tak_server",
            "enabled": True,
            "adapter_config": {"host": "tak.example.invalid", "port": 8089},
            "column_filter_ids": [column_id],
        },
    )
    assert r.status_code == 201, r.text
    publisher_id = r.json()["id"]

    r = client.patch(
        f"/v1/publishers/{publisher_id}",
        json={"plugin_type": "raw_cot", "adapter_config": {"transport": "udp"}},
    )
    assert r.status_code == 200, r.text
    assert r.json()["plugin_type"] == "raw_cot"

    r = client.get("/v1/publishers")
    assert r.status_code == 200, r.text
    assert r.json()[0]["column_filter_ids"] == [column_id]

    r = client.delete(f"/v1/publishers/{publisher_id}")
    assert r.status_code == 204, r.text

    for event_type in ("publisher.created", "publisher.updated", "publisher.deleted"):
        r = client.get(f"/v1/audit?event_type={event_type}")
        assert r.status_code == 200, r.text
        assert r.json()[0]["metadata"]["publisher_config_id"] == publisher_id


def test_plugin_config_requires_admin_role(client: TestClient) -> None:
    _create_viewer(client)
    r = client.post(
        "/v1/auth/login",
        json={
            "email": "viewer@example.com",
            "password": "viewer-pass-123",  # pragma: allowlist secret
        },
    )
    assert r.status_code == 200, r.text
    r = client.post(
        "/v1/auth/change-password",
        json={
            "current_password": "viewer-pass-123",  # pragma: allowlist secret
            "new_password": "viewer-pass-456",  # pragma: allowlist secret
        },
    )
    assert r.status_code == 200, r.text

    r = client.get("/v1/plugins")
    assert r.status_code == 403, r.text
    assert "requires role 'admin'" in r.json()["detail"]


def test_plugin_config_bearer_tokens_require_matching_scopes(client: TestClient) -> None:
    _login_admin(client)
    allowed = client.post(
        "/v1/auth/tokens",
        json={"name": "plugins", "scopes": ["plugins:read", "sources:write"]},
    ).json()["token"]
    denied = client.post(
        "/v1/auth/tokens",
        json={"name": "boards", "scopes": ["boards:read"]},
    ).json()["token"]
    client.post("/v1/auth/logout")

    r = client.get("/v1/plugins", headers={"Authorization": f"Bearer {allowed}"})
    assert r.status_code == 200, r.text
    r = client.post(
        "/v1/sources",
        headers={"Authorization": f"Bearer {allowed}"},
        json={"name": "Manual", "plugin_type": "manual"},
    )
    assert r.status_code == 201, r.text
    r = client.get("/v1/plugins", headers={"Authorization": f"Bearer {denied}"})
    assert r.status_code == 403, r.text
    assert r.json()["detail"] == "missing required token scope: plugins:read"


def test_plugin_config_write_tokens_can_be_limited_to_source_plugin(
    client: TestClient,
) -> None:
    _login_admin(client)
    token = client.post(
        "/v1/auth/tokens",
        json={"name": "manual-source", "scopes": ["sources:write:plugin:manual"]},
    ).json()["token"]
    client.post("/v1/auth/logout")

    r = client.post(
        "/v1/sources",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Manual", "plugin_type": "manual"},
    )
    assert r.status_code == 201, r.text

    r = client.post(
        "/v1/sources",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Webhook", "plugin_type": "http_webhook"},
    )
    assert r.status_code == 403, r.text
    assert (
        r.json()["detail"]
        == "missing required token scope: sources:write or sources:write:plugin:http_webhook"
    )


def test_plugin_config_write_tokens_can_be_limited_to_publisher_plugin(
    client: TestClient,
) -> None:
    _login_admin(client)
    token = client.post(
        "/v1/auth/tokens",
        json={"name": "raw-cot-publisher", "scopes": ["publishers:write:plugin:raw_cot"]},
    ).json()["token"]
    client.post("/v1/auth/logout")

    r = client.post(
        "/v1/publishers",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Raw", "plugin_type": "raw_cot"},
    )
    assert r.status_code == 201, r.text

    r = client.post(
        "/v1/publishers",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "TAK", "plugin_type": "tak_server"},
    )
    assert r.status_code == 403, r.text
    assert (
        r.json()["detail"]
        == "missing required token scope: publishers:write or publishers:write:plugin:tak_server"
    )


def test_plugin_scoped_source_token_controls_existing_source_plugin_only(
    client: TestClient,
) -> None:
    _login_admin(client)
    r = client.post("/v1/sources", json={"name": "Manual", "plugin_type": "manual"})
    assert r.status_code == 201, r.text
    source_id = r.json()["id"]
    token = client.post(
        "/v1/auth/tokens",
        json={"name": "manual-source", "scopes": ["sources:write:plugin:manual"]},
    ).json()["token"]
    client.post("/v1/auth/logout")

    r = client.patch(
        f"/v1/sources/{source_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Manual Renamed"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Manual Renamed"

    r = client.post(
        f"/v1/sources/{source_id}/test",
        headers={"Authorization": f"Bearer {token}"},
        json={"payload": {"name": "ALPHA"}},
    )
    assert r.status_code == 200, r.text
    assert r.json()["normalized"] == {"name": "ALPHA"}

    r = client.patch(
        f"/v1/sources/{source_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"plugin_type": "http_webhook"},
    )
    assert r.status_code == 403, r.text
    assert (
        r.json()["detail"]
        == "missing required token scope: sources:write or sources:write:plugin:http_webhook"
    )

    r = client.delete(
        f"/v1/sources/{source_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 204, r.text


def test_plugin_scoped_publisher_token_controls_existing_publisher_plugin_only(
    client: TestClient,
) -> None:
    _login_admin(client)
    r = client.post("/v1/publishers", json={"name": "Raw", "plugin_type": "raw_cot"})
    assert r.status_code == 201, r.text
    publisher_id = r.json()["id"]
    token = client.post(
        "/v1/auth/tokens",
        json={"name": "raw-cot", "scopes": ["publishers:write:plugin:raw_cot"]},
    ).json()["token"]
    client.post("/v1/auth/logout")

    r = client.patch(
        f"/v1/publishers/{publisher_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"name": "Raw Renamed"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Raw Renamed"

    r = client.patch(
        f"/v1/publishers/{publisher_id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"plugin_type": "tak_server"},
    )
    assert r.status_code == 403, r.text
    assert (
        r.json()["detail"]
        == "missing required token scope: publishers:write or publishers:write:plugin:tak_server"
    )

    r = client.delete(
        f"/v1/publishers/{publisher_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 204, r.text


def test_deleted_source_row_is_removed_from_database(client: TestClient) -> None:
    _login_admin(client)
    r = client.post("/v1/sources", json={"name": "Manual", "plugin_type": "manual"})
    assert r.status_code == 201, r.text
    source_id = UUID(r.json()["id"])

    r = client.delete(f"/v1/sources/{source_id}")
    assert r.status_code == 204, r.text

    from target_workspace.db import get_engine
    from target_workspace.db.tables import SourceConfigTable

    with Session(get_engine()) as session:
        assert (
            session.exec(select(SourceConfigTable).where(SourceConfigTable.id == source_id)).first()
            is None
        )
