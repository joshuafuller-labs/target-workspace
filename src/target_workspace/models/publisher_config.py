"""PublisherConfig — per-Publisher configuration row (TDD chunk 5b)."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class PublisherConfig(BaseModel):
    """Workspace-level config for one Publisher plugin instance."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=120, description="Operator-facing label.")
    plugin_type: str = Field(
        min_length=1,
        max_length=80,
        description=(
            "Stable identifier of the Publisher plugin to instantiate "
            "(e.g. 'tak_server', 'raw_cot', 'webhook_out')."
        ),
    )
    enabled: bool = Field(default=True)
    adapter_config: dict[str, Any] = Field(
        default_factory=dict,
        description="Plugin-specific config: endpoint, cert bundle ref, auth, template.",
    )
    column_filter_ids: list[UUID] = Field(
        default_factory=list,
        description="Columns that trigger publishing. Empty = publish on configured triggers only.",
    )
