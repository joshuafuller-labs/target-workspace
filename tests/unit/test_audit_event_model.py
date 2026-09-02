"""Tests for AuditEvent (TDD chunk 3).

The append-only event in the audit log. Append-only is enforced at the
persistence layer; this model is the data shape.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from target_workspace.models.audit_event import AuditEvent, EventType

pytestmark = [pytest.mark.fast]


@pytest.fixture
def base_kwargs() -> dict[str, Any]:
    return {
        "target_id": uuid4(),
        "actor_id": uuid4(),
        "event_type": "created",
        "occurred_at": datetime(2026, 5, 16, 21, 45, 0, tzinfo=UTC),
    }


def test_requires_target_id(base_kwargs: dict[str, Any]) -> None:
    kwargs = {**base_kwargs}
    del kwargs["target_id"]
    with pytest.raises(ValidationError):
        AuditEvent(**kwargs)


def test_requires_actor_id(base_kwargs: dict[str, Any]) -> None:
    kwargs = {**base_kwargs}
    del kwargs["actor_id"]
    with pytest.raises(ValidationError):
        AuditEvent(**kwargs)


def test_requires_event_type(base_kwargs: dict[str, Any]) -> None:
    kwargs = {**base_kwargs}
    del kwargs["event_type"]
    with pytest.raises(ValidationError):
        AuditEvent(**kwargs)


def test_requires_occurred_at(base_kwargs: dict[str, Any]) -> None:
    kwargs = {**base_kwargs}
    del kwargs["occurred_at"]
    with pytest.raises(ValidationError):
        AuditEvent(**kwargs)


def test_event_type_must_be_known(base_kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        AuditEvent(**{**base_kwargs, "event_type": "totally_invented"})


@pytest.mark.parametrize(
    "event_type",
    ["created", "updated", "transitioned", "approved", "rejected", "published", "deleted"],
)
def test_all_known_event_types_accepted(base_kwargs: dict[str, Any], event_type: EventType) -> None:
    AuditEvent(**{**base_kwargs, "event_type": event_type})


def test_transition_carries_columns(base_kwargs: dict[str, Any]) -> None:
    from_col = uuid4()
    to_col = uuid4()
    ev = AuditEvent(
        **{
            **base_kwargs,
            "event_type": "transitioned",
            "from_column_id": from_col,
            "to_column_id": to_col,
        },
    )
    assert ev.from_column_id == from_col
    assert ev.to_column_id == to_col


def test_id_is_generated(base_kwargs: dict[str, Any]) -> None:
    ev = AuditEvent(**base_kwargs)
    assert isinstance(ev.id, UUID)


def test_justification_optional(base_kwargs: dict[str, Any]) -> None:
    assert AuditEvent(**base_kwargs).justification is None


def test_metadata_defaults_empty_dict(base_kwargs: dict[str, Any]) -> None:
    assert AuditEvent(**base_kwargs).metadata == {}


def test_round_trip_json(base_kwargs: dict[str, Any]) -> None:
    e1 = AuditEvent(**base_kwargs)
    e2 = AuditEvent.model_validate_json(e1.model_dump_json())
    assert e1 == e2


def test_forbid_extra(base_kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        AuditEvent(**{**base_kwargs, "totally_invented": "x"})
