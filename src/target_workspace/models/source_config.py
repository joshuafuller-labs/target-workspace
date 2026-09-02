"""SourceConfig — per-Source configuration row (TDD chunk 5a).

Holds the runtime config that the workspace owner supplies for a given
Source adapter: which plugin type, its connection/auth details, the
normalization map for ingest payload -> Target fields, and the
PromotionPolicy reference applied to detections from this source.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class SourceConfig(BaseModel):
    """Workspace-level config for one Source plugin instance."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=120, description="Operator-facing label.")
    plugin_type: str = Field(
        min_length=1,
        max_length=80,
        description=(
            "Stable identifier of the Source plugin to instantiate "
            "(e.g. 'manual', 'http_webhook', 'cot_in')."
        ),
    )
    enabled: bool = Field(default=True)
    adapter_config: dict[str, Any] = Field(
        default_factory=dict,
        description="Plugin-specific config: auth, endpoints, polling interval, etc.",
    )
    normalization_map: dict[str, Any] = Field(
        default_factory=dict,
        description="Mapping rules (jq/jmespath-style) from source payload to Target fields.",
    )
    promotion_policy_id: UUID | None = Field(
        default=None,
        description=(
            "PromotionPolicy applied to detections from this source. "
            "None = workspace default policy."
        ),
    )
