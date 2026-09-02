"""PromotionPolicy — the autonomy spectrum as a row (TDD chunk 4).

Three modes share the same engine code path (per ADR 0008):
- gated:        operator must approve every required-stage transition
- conditional:  auto-promote when confidence ≥ min_confidence
- autonomous:   skip review, route to auto_publish_column on arrival

MVP ships only `gated` in the engine; the schema supports all three so
the post-MVP path is just enabling the engine branches.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

PromotionMode = Literal["gated", "conditional", "autonomous"]


class PromotionPolicy(BaseModel):
    """How a Target moves between Columns under this policy."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    id: UUID = Field(default_factory=uuid4)
    mode: PromotionMode = Field(description="Promotion mode.")
    min_confidence: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Required for `conditional` mode.",
    )
    required_stages: list[UUID] = Field(
        default_factory=list,
        description="Column IDs the Target must pass through under this policy.",
    )
    approval_roles: list[str] = Field(
        default_factory=list,
        description="Role names allowed to promote past gated stages.",
    )
    auto_publish_column_id: UUID | None = Field(
        default=None,
        description="Required for `autonomous`. Column whose entry triggers publisher dispatch.",
    )
    on_low_confidence_route_to_column_id: UUID | None = Field(
        default=None,
        description=(
            "Optional. In `conditional` mode, below-threshold detections route here instead "
            "of being dropped."
        ),
    )

    @model_validator(mode="after")
    def _enforce_mode_invariants(self) -> PromotionPolicy:
        if self.mode == "conditional" and self.min_confidence is None:
            msg = "conditional mode requires min_confidence"
            raise ValueError(msg)
        if self.mode == "autonomous" and self.auto_publish_column_id is None:
            msg = "autonomous mode requires auto_publish_column_id"
            raise ValueError(msg)
        return self
