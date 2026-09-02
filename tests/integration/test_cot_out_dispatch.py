"""CoT-out publisher pipeline — dispatch on target.created (tw-50i5).

The publisher contract + PublisherConfigTable + raw_cot / tak_server
publishers + dispatch on column transitions all already shipped. The
gap this ticket closes: publishers fire ONLY on transition today, not
on initial target creation. For 'CoT-native' to be honest, a new target
should propagate to TAK immediately, not wait for its first column
move.

Assumption documented in tw-50i5:
  - Wire publisher dispatch on POST /v1/targets so newly-created targets
    fan to publishers whose column_filter_ids include the initial column.
  - target.updated dispatch (lat/lon changes via PATCH) is a follow-up.
  - Lifespan startup scan of PublisherConfig is treated as a no-op
    validation pass at MVP (publishers are stateless event-driven, not
    background tasks).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.fast]


def _login_admin(c: TestClient) -> None:
    r = c.post(
        "/v1/auth/login",
        json={"email": "admin@example.com", "password": "test-pw"},
    )
    assert r.status_code == 200, r.text


def _make_board(c: TestClient) -> dict[str, Any]:
    r = c.post(
        "/v1/boards",
        json={
            "name": "Strike",
            "columns": [{"name": "Detect", "order": 0}, {"name": "Engage", "order": 1}],
        },
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_publishers_dispatched_on_target_created(client: TestClient) -> None:
    """A new target in a column with a matching PublisherConfig should
    trigger a publisher dispatch immediately — not only after a transition."""
    from target_workspace.db.tables import PublisherConfigTable

    _login_admin(client)
    board = _make_board(client)
    column_id = board["columns"][0]["id"]

    # Stand up a recording publisher and a PublisherConfig pointing at it.
    received: list[dict[str, Any]] = []

    from target_workspace.plugins.loader import register_publisher

    class RecordingPublisher:
        name = "recording-test"

        def publish(self, *, target, adapter_config):  # type: ignore[no-untyped-def]
            received.append(
                {
                    "target_id": str(target.id),
                    "config": dict(adapter_config),
                }
            )

    register_publisher("recording-test", RecordingPublisher)

    # Insert PublisherConfig with column_filter_ids = [column_id].
    from sqlmodel import Session

    from target_workspace.db import get_engine

    with Session(get_engine()) as s:
        from target_workspace.db.tables import WorkspaceTable

        ws = s.exec(__import__("sqlmodel").select(WorkspaceTable)).first()
        assert ws is not None
        cfg = PublisherConfigTable(
            workspace_id=ws.id,
            plugin_type="recording-test",
            name="rec",
            adapter_config={},
            column_filter_ids=[str(column_id)],
            enabled=True,
            created_at=datetime.now(tz=UTC),
        )
        s.add(cfg)
        s.commit()

    # Create a target in that column via /v1/capture (cheapest creation path)
    r = client.post(
        "/v1/capture",
        data={
            "title": "Recon Subject",
            "lat": "35.6",
            "lon": "-82.5",
            "board_id": board["id"],
            "column_id": column_id,
        },
    )
    assert r.status_code == 201, r.text

    assert len(received) >= 1, f"expected publisher to receive the new target; received={received}"
