"""Tests for the Target Pydantic model.

Written before the implementation in src/target_workspace/models/target.py.
Each test exercises a single invariant of the schema; together they pin
down the contract.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from pydantic import ValidationError

from target_workspace.models.target import Target

pytestmark = [pytest.mark.fast]


@pytest.fixture
def base_kwargs() -> dict[str, Any]:
    """Minimum kwargs to construct a valid Target."""
    return {
        "name": "BISON-01",
        "lat": 33.4484,
        "lon": -112.0740,
        "time": datetime(2026, 5, 16, 21, 45, 0, tzinfo=UTC),
    }


class TestTargetRequiredFields:
    """Per ADR 0013, missing required fields raise ValidationError at construction."""

    def test_requires_name(self, base_kwargs: dict[str, Any]) -> None:
        kwargs = {**base_kwargs}
        del kwargs["name"]
        with pytest.raises(ValidationError):
            Target(**kwargs)

    def test_requires_lat(self, base_kwargs: dict[str, Any]) -> None:
        kwargs = {**base_kwargs}
        del kwargs["lat"]
        with pytest.raises(ValidationError):
            Target(**kwargs)

    def test_requires_lon(self, base_kwargs: dict[str, Any]) -> None:
        kwargs = {**base_kwargs}
        del kwargs["lon"]
        with pytest.raises(ValidationError):
            Target(**kwargs)

    def test_requires_time(self, base_kwargs: dict[str, Any]) -> None:
        """Per ADR 0010, time is source-provided and required."""
        kwargs = {**base_kwargs}
        del kwargs["time"]
        with pytest.raises(ValidationError):
            Target(**kwargs)


class TestTargetValidation:
    def test_name_min_length(self, base_kwargs: dict[str, Any]) -> None:
        with pytest.raises(ValidationError):
            Target(**{**base_kwargs, "name": ""})

    def test_name_max_length(self, base_kwargs: dict[str, Any]) -> None:
        with pytest.raises(ValidationError):
            Target(**{**base_kwargs, "name": "x" * 201})

    def test_lat_above_range(self, base_kwargs: dict[str, Any]) -> None:
        with pytest.raises(ValidationError):
            Target(**{**base_kwargs, "lat": 90.1})

    def test_lat_below_range(self, base_kwargs: dict[str, Any]) -> None:
        with pytest.raises(ValidationError):
            Target(**{**base_kwargs, "lat": -90.1})

    def test_lon_above_range(self, base_kwargs: dict[str, Any]) -> None:
        with pytest.raises(ValidationError):
            Target(**{**base_kwargs, "lon": 180.1})

    def test_lon_below_range(self, base_kwargs: dict[str, Any]) -> None:
        with pytest.raises(ValidationError):
            Target(**{**base_kwargs, "lon": -180.1})

    def test_confidence_below_zero(self, base_kwargs: dict[str, Any]) -> None:
        with pytest.raises(ValidationError):
            Target(**{**base_kwargs, "confidence": -0.01})

    def test_confidence_above_one(self, base_kwargs: dict[str, Any]) -> None:
        with pytest.raises(ValidationError):
            Target(**{**base_kwargs, "confidence": 1.01})

    def test_ce_must_be_non_negative(self, base_kwargs: dict[str, Any]) -> None:
        with pytest.raises(ValidationError):
            Target(**{**base_kwargs, "ce": -1.0})

    def test_le_must_be_non_negative(self, base_kwargs: dict[str, Any]) -> None:
        with pytest.raises(ValidationError):
            Target(**{**base_kwargs, "le": -1.0})

    def test_version_must_be_at_least_one(self, base_kwargs: dict[str, Any]) -> None:
        with pytest.raises(ValidationError):
            Target(**{**base_kwargs, "version": 0})


class TestTargetDefaults:
    def test_generates_uuid(self, base_kwargs: dict[str, Any]) -> None:
        t = Target(**base_kwargs)
        assert isinstance(t.id, UUID)

    def test_two_targets_have_distinct_ids(self, base_kwargs: dict[str, Any]) -> None:
        t1 = Target(**base_kwargs)
        t2 = Target(**base_kwargs)
        assert t1.id != t2.id

    def test_starts_at_version_one(self, base_kwargs: dict[str, Any]) -> None:
        t = Target(**base_kwargs)
        assert t.version == 1

    def test_default_cot_type_is_neutral(self, base_kwargs: dict[str, Any]) -> None:
        """Per ADR 0008 (malleability), default cot_type is neutral 'unknown ground'."""
        t = Target(**base_kwargs)
        assert t.cot_type == "a-u-G"

    def test_optional_geometry_defaults_none(self, base_kwargs: dict[str, Any]) -> None:
        t = Target(**base_kwargs)
        assert t.hae is None
        assert t.ce is None
        assert t.le is None

    def test_optional_signal_defaults_none(self, base_kwargs: dict[str, Any]) -> None:
        t = Target(**base_kwargs)
        assert t.confidence is None
        assert t.category is None
        assert t.stale is None

    def test_custom_fields_defaults_empty_dict(self, base_kwargs: dict[str, Any]) -> None:
        """Per ADR 0008 (malleability), workspaces extend via custom_fields."""
        t = Target(**base_kwargs)
        assert t.custom_fields == {}

    def test_custom_fields_independent_per_instance(self, base_kwargs: dict[str, Any]) -> None:
        """Default-factory must not share a single dict reference across instances."""
        t1 = Target(**base_kwargs)
        t2 = Target(**base_kwargs)
        t1.custom_fields["jiptl_priority"] = 4
        assert "jiptl_priority" not in t2.custom_fields


class TestTargetSerialization:
    def test_round_trip_json(self, base_kwargs: dict[str, Any]) -> None:
        t1 = Target(**base_kwargs)
        json_str = t1.model_dump_json()
        t2 = Target.model_validate_json(json_str)
        assert t1 == t2

    def test_forbid_extra_fields(self, base_kwargs: dict[str, Any]) -> None:
        """Per ADR 0013, schemas use additionalProperties: false."""
        with pytest.raises(ValidationError):
            Target(**{**base_kwargs, "totally_invented_field": "nope"})

    def test_custom_fields_accepts_workspace_specific_data(
        self, base_kwargs: dict[str, Any]
    ) -> None:
        """custom_fields is the malleability seam — arbitrary JSON-compatible values."""
        t = Target(
            **base_kwargs,
            custom_fields={"jiptl_priority": 4, "cde_level": "LV-2", "approved_by": "MAJ Holloway"},
        )
        assert t.custom_fields["jiptl_priority"] == 4
