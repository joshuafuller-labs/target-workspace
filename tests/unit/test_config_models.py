"""Tests for SourceConfig, PublisherConfig, Workspace, User (TDD chunk 5)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from target_workspace.models.publisher_config import PublisherConfig
from target_workspace.models.source_config import SourceConfig
from target_workspace.models.workspace import User, Workspace

pytestmark = [pytest.mark.fast]


class TestSourceConfig:
    def test_minimal_construction(self) -> None:
        s = SourceConfig(name="Manual entry", plugin_type="manual")
        assert s.enabled is True
        assert s.adapter_config == {}
        assert s.normalization_map == {}
        assert s.promotion_policy_id is None
        assert isinstance(s.id, UUID)

    def test_requires_name(self) -> None:
        with pytest.raises(ValidationError):
            SourceConfig(plugin_type="manual")  # type: ignore[call-arg]

    def test_requires_plugin_type(self) -> None:
        with pytest.raises(ValidationError):
            SourceConfig(name="x")  # type: ignore[call-arg]

    def test_name_min_length(self) -> None:
        with pytest.raises(ValidationError):
            SourceConfig(name="", plugin_type="manual")

    def test_forbid_extra(self) -> None:
        with pytest.raises(ValidationError):
            SourceConfig(name="x", plugin_type="manual", invented="nope")  # type: ignore[call-arg]

    def test_round_trip(self) -> None:
        s1 = SourceConfig(
            name="MQ-9 ATR",
            plugin_type="http_webhook",
            adapter_config={"endpoint": "/v1/ingest/mq9", "auth": "bearer"},
            normalization_map={"target.lat": "$.detection.lat"},
            promotion_policy_id=uuid4(),
        )
        s2 = SourceConfig.model_validate_json(s1.model_dump_json())
        assert s1 == s2


class TestPublisherConfig:
    def test_minimal_construction(self) -> None:
        p = PublisherConfig(name="TAK Server prod", plugin_type="tak_server")
        assert p.enabled is True
        assert p.column_filter_ids == []
        assert isinstance(p.id, UUID)

    def test_requires_name(self) -> None:
        with pytest.raises(ValidationError):
            PublisherConfig(plugin_type="tak_server")  # type: ignore[call-arg]

    def test_requires_plugin_type(self) -> None:
        with pytest.raises(ValidationError):
            PublisherConfig(name="x")  # type: ignore[call-arg]

    def test_forbid_extra(self) -> None:
        with pytest.raises(ValidationError):
            PublisherConfig(name="x", plugin_type="tak_server", invented="nope")  # type: ignore[call-arg]

    def test_round_trip(self) -> None:
        p1 = PublisherConfig(
            name="raw CoT",
            plugin_type="raw_cot",
            adapter_config={"endpoint": "udp://239.2.3.1:6969"},
            column_filter_ids=[uuid4(), uuid4()],
        )
        p2 = PublisherConfig.model_validate_json(p1.model_dump_json())
        assert p1 == p2


class TestWorkspace:
    def test_minimal_construction(self) -> None:
        w = Workspace(name="Personal", created_at=datetime(2026, 5, 16, tzinfo=UTC))
        assert isinstance(w.id, UUID)

    def test_requires_name(self) -> None:
        with pytest.raises(ValidationError):
            Workspace(created_at=datetime(2026, 5, 16, tzinfo=UTC))  # type: ignore[call-arg]

    def test_requires_created_at(self) -> None:
        with pytest.raises(ValidationError):
            Workspace(name="x")  # type: ignore[call-arg]

    def test_name_min_length(self) -> None:
        with pytest.raises(ValidationError):
            Workspace(name="", created_at=datetime(2026, 5, 16, tzinfo=UTC))


class TestUser:
    def _kwargs(self) -> dict[str, object]:
        return {
            "workspace_id": uuid4(),
            "email": "j@example.com",
            "display_name": "J Fuller",
            "created_at": datetime(2026, 5, 16, tzinfo=UTC),
        }

    def test_minimal_construction(self) -> None:
        u = User(**self._kwargs())
        assert u.role == "viewer"

    def test_role_must_be_known(self) -> None:
        with pytest.raises(ValidationError):
            User(**{**self._kwargs(), "role": "god-mode"})

    def test_login_identifier_accepts_non_email_username(self) -> None:
        u = User(**{**self._kwargs(), "email": "incident-commander"})
        assert u.email == "incident-commander"

    def test_login_identifier_must_not_be_empty(self) -> None:
        with pytest.raises(ValidationError):
            User(**{**self._kwargs(), "email": ""})

    def test_round_trip(self) -> None:
        u1 = User(**{**self._kwargs(), "role": "admin"})
        u2 = User.model_validate_json(u1.model_dump_json())
        assert u1 == u2
