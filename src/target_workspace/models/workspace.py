"""Workspace + User — identity + RBAC seam for MVP (TDD chunk 5c).

MVP ships with a single workspace and a single admin user. The schema
supports multi-workspace + multi-user from day one so OIDC / multi-tenancy
slot in without rewriting.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

Role = Literal["admin", "analyst", "operator", "viewer"]


class Workspace(BaseModel):
    """A single workspace; the top-level tenant boundary."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    id: UUID = Field(default_factory=uuid4)
    name: str = Field(min_length=1, max_length=120)
    created_at: datetime = Field(description="When the workspace was created (UTC).")


class User(BaseModel):
    """A user within a workspace."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    id: UUID = Field(default_factory=uuid4)
    workspace_id: UUID = Field(description="Workspace this user belongs to.")
    email: str = Field(min_length=1, max_length=320, description="Login identifier.")
    display_name: str = Field(min_length=1, max_length=120)
    role: Role = Field(default="viewer", description="Workspace-scoped RBAC role.")
    created_at: datetime = Field(description="When the user was created (UTC).")
