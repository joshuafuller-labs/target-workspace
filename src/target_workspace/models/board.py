"""Board + Column models — the workspace workflow definition (TDD chunk 2).

Per ADR 0008 (malleability) the column set is **data**, not code. Workspace
owners define their own stage names, ordering, WIP limits, approval gates,
and transition rules. Bundled templates (F3EAD, D3A, LE case, SAR) are
example data, not core features.

Per ADR 0013 (API client-agnostic) we use `extra="forbid"` so generated
clients produce strict types.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Column(BaseModel):
    """A single stage within a Board.

    Workspace-defined name and order. Optional WIP limit, color, and an
    approval-required flag for gated transitions.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    id: UUID = Field(default_factory=uuid4, description="Server-issued stable identifier.")
    name: str = Field(min_length=1, max_length=80, description="Workspace-defined stage label.")
    order: int = Field(ge=0, description="Sort order within the Board (0 = leftmost).")
    wip_limit: int | None = Field(
        default=None,
        ge=1,
        description="Soft WIP limit; exceeding triggers a board notification.",
    )
    color: str | None = Field(
        default=None,
        max_length=32,
        description="Optional UI hint; theme-dependent.",
    )
    requires_approval: bool = Field(
        default=False,
        description="If true, entry into this column gates on an approval action.",
    )
    expected_approving_roles: list[str] = Field(
        default_factory=list,
        description=(
            "tw-cck: dropdown hint for the SPA ApprovalPrompt — role "
            "strings that the workspace expects to satisfy this gate. "
            "Free-text fallback when empty. Backend does NOT enforce."
        ),
    )


TransitionRule = Literal["unrestricted", "sequential"]

# Per ADR 0008 + ADR 0011, theme is data, not code. The bundled themes are
# example palettes anyone can fork. New themes drop in as data + frontend CSS
# without core changes.
ThemeName = Literal["neutral", "tactical", "federal", "sar", "ics"]


class Board(BaseModel):
    """A workspace workflow: an ordered set of Columns plus transition rules.

    Boards are pure data. The bundled templates (F3EAD, D3A, JP 3-60, F2T2EA,
    LE case, SAR mission) are example Boards anyone can fork or replace.
    """

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    id: UUID = Field(default_factory=uuid4, description="Server-issued stable identifier.")
    name: str = Field(min_length=1, max_length=120, description="Workspace-defined board name.")
    columns: list[Column] = Field(
        min_length=1,
        description="Ordered list of stages. Sorted by `order` on construction.",
    )
    transitions: TransitionRule = Field(
        default="unrestricted",
        description=(
            "`unrestricted` allows any column-to-column move. `sequential` permits only "
            "forward-by-one moves; backwards / skips disallowed (workflow engine enforces)."
        ),
    )
    theme: ThemeName = Field(
        default="neutral",
        description=(
            "Visual theme applied to the SPA when this board is selected. "
            "Workspace-data per ADR 0008; bundled themes ship in the frontend."
        ),
    )

    @model_validator(mode="after")
    def _enforce_unique_columns(self) -> Board:
        names = [c.name for c in self.columns]
        if len(names) != len(set(names)):
            msg = "column names must be unique within a Board"
            raise ValueError(msg)
        orders = [c.order for c in self.columns]
        if len(orders) != len(set(orders)):
            msg = "column orders must be unique within a Board"
            raise ValueError(msg)
        # Sort by order for consistent downstream behavior
        object.__setattr__(self, "columns", sorted(self.columns, key=lambda c: c.order))
        return self

    def can_move(self, from_column_id: UUID, to_column_id: UUID) -> bool:
        """Return whether a transition between two of this Board's columns is allowed."""
        idx_by_id = {c.id: i for i, c in enumerate(self.columns)}
        if from_column_id not in idx_by_id or to_column_id not in idx_by_id:
            return False
        if self.transitions == "unrestricted":
            return True
        # sequential: forward-by-one only
        return idx_by_id[to_column_id] == idx_by_id[from_column_id] + 1
