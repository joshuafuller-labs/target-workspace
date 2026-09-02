"""AuditEvent — append-only record of state changes (TDD chunk 3).

Append-only is enforced at the persistence layer (no UPDATE / DELETE).
This Pydantic model is the data shape that gets written.

Per ADR 0013 (API client-agnostic) extra=forbid for strict client codegen.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

EventType = Literal[
    "created",
    "updated",
    "transitioned",
    "nominated",
    "approved",
    "rejected",
    "published",
    "deleted",
    "reordered",
]


class AuditEvent(BaseModel):
    """An immutable record of one state-affecting action on a Target."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    id: UUID = Field(default_factory=uuid4)
    target_id: UUID = Field(description="Target this event is about.")
    actor_id: UUID = Field(description="User who caused this event.")
    event_type: EventType = Field(description="What happened.")
    occurred_at: datetime = Field(description="When the event happened (UTC).")

    # Set only on `transitioned`
    from_column_id: UUID | None = Field(default=None)
    to_column_id: UUID | None = Field(default=None)

    justification: str | None = Field(
        default=None,
        max_length=2000,
        description="Optional human-recorded reason for the action.",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary machine-readable context (source ref, model id, etc.).",
    )
