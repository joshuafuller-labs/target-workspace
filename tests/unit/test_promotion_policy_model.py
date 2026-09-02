"""Tests for PromotionPolicy (TDD chunk 4)."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from target_workspace.models.promotion_policy import PromotionPolicy

pytestmark = [pytest.mark.fast]


@pytest.fixture
def gated_kwargs() -> dict[str, Any]:
    return {"mode": "gated", "approval_roles": ["analyst", "supervisor"]}


@pytest.fixture
def conditional_kwargs() -> dict[str, Any]:
    return {"mode": "conditional", "min_confidence": 0.85}


@pytest.fixture
def autonomous_kwargs() -> dict[str, Any]:
    return {"mode": "autonomous", "auto_publish_column_id": uuid4()}


def test_gated_default_construction(gated_kwargs: dict[str, Any]) -> None:
    p = PromotionPolicy(**gated_kwargs)
    assert p.mode == "gated"
    assert p.min_confidence is None


def test_conditional_requires_min_confidence() -> None:
    with pytest.raises(ValidationError):
        PromotionPolicy(mode="conditional")


def test_conditional_min_confidence_range(conditional_kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        PromotionPolicy(**{**conditional_kwargs, "min_confidence": -0.1})
    with pytest.raises(ValidationError):
        PromotionPolicy(**{**conditional_kwargs, "min_confidence": 1.1})


def test_autonomous_requires_auto_publish_column(autonomous_kwargs: dict[str, Any]) -> None:
    p = PromotionPolicy(**autonomous_kwargs)
    assert p.auto_publish_column_id is not None
    with pytest.raises(ValidationError):
        PromotionPolicy(mode="autonomous")


def test_mode_must_be_known() -> None:
    with pytest.raises(ValidationError):
        PromotionPolicy(mode="invented")


def test_id_generated(gated_kwargs: dict[str, Any]) -> None:
    assert isinstance(PromotionPolicy(**gated_kwargs).id, UUID)


def test_round_trip_json(gated_kwargs: dict[str, Any]) -> None:
    p1 = PromotionPolicy(**gated_kwargs)
    p2 = PromotionPolicy.model_validate_json(p1.model_dump_json())
    assert p1 == p2


def test_forbid_extra(gated_kwargs: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        PromotionPolicy(**{**gated_kwargs, "totally_invented": "x"})


def test_required_stages_default_empty(gated_kwargs: dict[str, Any]) -> None:
    assert PromotionPolicy(**gated_kwargs).required_stages == []


def test_approval_roles_default_empty() -> None:
    assert PromotionPolicy(mode="gated").approval_roles == []


def test_conditional_optional_low_confidence_route(conditional_kwargs: dict[str, Any]) -> None:
    col = uuid4()
    p = PromotionPolicy(**{**conditional_kwargs, "on_low_confidence_route_to_column_id": col})
    assert p.on_low_confidence_route_to_column_id == col
