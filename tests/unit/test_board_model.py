"""Tests for the Board + Column Pydantic models (TDD chunk 2).

Per ADR 0008 (malleability) the column set is data, not code — workspace
owners define their own. Tests pin: required fields, ordering, uniqueness
within a Board, transition rules, defaults, JSON round-trip, extra=forbid.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import pytest
from pydantic import ValidationError

from target_workspace.models.board import Board, Column

pytestmark = [pytest.mark.fast]


@pytest.fixture
def base_column_kwargs() -> dict[str, Any]:
    return {"name": "FIND", "order": 0}


@pytest.fixture
def base_board_kwargs() -> dict[str, Any]:
    return {
        "name": "JSOTF F3EAD",
        "columns": [
            {"name": "FIND", "order": 0},
            {"name": "FIX", "order": 1},
            {"name": "FINISH", "order": 2},
        ],
    }


class TestColumnRequiredFields:
    def test_requires_name(self, base_column_kwargs: dict[str, Any]) -> None:
        kwargs = {**base_column_kwargs}
        del kwargs["name"]
        with pytest.raises(ValidationError):
            Column(**kwargs)

    def test_requires_order(self, base_column_kwargs: dict[str, Any]) -> None:
        kwargs = {**base_column_kwargs}
        del kwargs["order"]
        with pytest.raises(ValidationError):
            Column(**kwargs)


class TestColumnValidation:
    def test_name_min_length(self, base_column_kwargs: dict[str, Any]) -> None:
        with pytest.raises(ValidationError):
            Column(**{**base_column_kwargs, "name": ""})

    def test_name_max_length(self, base_column_kwargs: dict[str, Any]) -> None:
        with pytest.raises(ValidationError):
            Column(**{**base_column_kwargs, "name": "x" * 81})

    def test_order_must_be_non_negative(self, base_column_kwargs: dict[str, Any]) -> None:
        with pytest.raises(ValidationError):
            Column(**{**base_column_kwargs, "order": -1})

    def test_wip_limit_must_be_positive_when_set(self, base_column_kwargs: dict[str, Any]) -> None:
        with pytest.raises(ValidationError):
            Column(**{**base_column_kwargs, "wip_limit": 0})


class TestColumnDefaults:
    def test_generates_uuid(self, base_column_kwargs: dict[str, Any]) -> None:
        c = Column(**base_column_kwargs)
        assert isinstance(c.id, UUID)

    def test_wip_limit_defaults_none(self, base_column_kwargs: dict[str, Any]) -> None:
        c = Column(**base_column_kwargs)
        assert c.wip_limit is None

    def test_color_defaults_none(self, base_column_kwargs: dict[str, Any]) -> None:
        c = Column(**base_column_kwargs)
        assert c.color is None

    def test_requires_approval_defaults_false(self, base_column_kwargs: dict[str, Any]) -> None:
        c = Column(**base_column_kwargs)
        assert c.requires_approval is False

    def test_forbid_extra_fields(self, base_column_kwargs: dict[str, Any]) -> None:
        with pytest.raises(ValidationError):
            Column(**{**base_column_kwargs, "totally_invented": "nope"})


class TestBoardRequiredFields:
    def test_requires_name(self, base_board_kwargs: dict[str, Any]) -> None:
        kwargs = {**base_board_kwargs}
        del kwargs["name"]
        with pytest.raises(ValidationError):
            Board(**kwargs)

    def test_requires_columns(self, base_board_kwargs: dict[str, Any]) -> None:
        kwargs = {**base_board_kwargs}
        del kwargs["columns"]
        with pytest.raises(ValidationError):
            Board(**kwargs)


class TestBoardValidation:
    def test_at_least_one_column(self, base_board_kwargs: dict[str, Any]) -> None:
        with pytest.raises(ValidationError):
            Board(**{**base_board_kwargs, "columns": []})

    def test_column_names_must_be_unique(self, base_board_kwargs: dict[str, Any]) -> None:
        with pytest.raises(ValidationError) as exc_info:
            Board(
                **{
                    **base_board_kwargs,
                    "columns": [
                        {"name": "FIND", "order": 0},
                        {"name": "FIND", "order": 1},
                    ],
                }
            )
        assert "unique" in str(exc_info.value).lower()

    def test_column_orders_must_be_unique(self, base_board_kwargs: dict[str, Any]) -> None:
        with pytest.raises(ValidationError) as exc_info:
            Board(
                **{
                    **base_board_kwargs,
                    "columns": [
                        {"name": "A", "order": 0},
                        {"name": "B", "order": 0},
                    ],
                }
            )
        assert "order" in str(exc_info.value).lower()

    def test_name_min_length(self, base_board_kwargs: dict[str, Any]) -> None:
        with pytest.raises(ValidationError):
            Board(**{**base_board_kwargs, "name": ""})


class TestBoardDefaults:
    def test_generates_uuid(self, base_board_kwargs: dict[str, Any]) -> None:
        b = Board(**base_board_kwargs)
        assert isinstance(b.id, UUID)

    def test_columns_sorted_by_order(self, base_board_kwargs: dict[str, Any]) -> None:
        b = Board(
            **{
                **base_board_kwargs,
                "columns": [
                    {"name": "C", "order": 2},
                    {"name": "A", "order": 0},
                    {"name": "B", "order": 1},
                ],
            }
        )
        assert [c.name for c in b.columns] == ["A", "B", "C"]

    def test_transitions_defaults_unrestricted(self, base_board_kwargs: dict[str, Any]) -> None:
        b = Board(**base_board_kwargs)
        assert b.transitions == "unrestricted"

    def test_forbid_extra_fields(self, base_board_kwargs: dict[str, Any]) -> None:
        with pytest.raises(ValidationError):
            Board(**{**base_board_kwargs, "totally_invented": "nope"})


class TestBoardTransitionRules:
    def test_can_move_unrestricted(self, base_board_kwargs: dict[str, Any]) -> None:
        b = Board(**base_board_kwargs)
        # Any pair is allowed
        assert b.can_move(b.columns[0].id, b.columns[2].id) is True

    def test_can_move_sequential_forward_only(self, base_board_kwargs: dict[str, Any]) -> None:
        b = Board(**{**base_board_kwargs, "transitions": "sequential"})
        # Move forward one column allowed
        assert b.can_move(b.columns[0].id, b.columns[1].id) is True
        # Skipping not allowed
        assert b.can_move(b.columns[0].id, b.columns[2].id) is False
        # Backward not allowed
        assert b.can_move(b.columns[1].id, b.columns[0].id) is False


class TestBoardSerialization:
    def test_round_trip_json(self, base_board_kwargs: dict[str, Any]) -> None:
        b1 = Board(**base_board_kwargs)
        b2 = Board.model_validate_json(b1.model_dump_json())
        assert b1 == b2
