"""Data models for Target Workspace.

Per ADR 0013 (API client-agnostic), these Pydantic models are the public
schema surface. FastAPI generates the OpenAPI spec from their type hints;
plugin authors and third-party integrators codegen clients from that spec.

Per ADR 0008 (malleability), the core models are neutral; workspace-specific
shape (column names, classification schemes, theme, custom fields) lives
elsewhere as configurable data.
"""

from target_workspace.models.audit_event import AuditEvent, EventType
from target_workspace.models.board import Board, Column, TransitionRule
from target_workspace.models.promotion_policy import PromotionMode, PromotionPolicy
from target_workspace.models.publisher_config import PublisherConfig
from target_workspace.models.source_config import SourceConfig
from target_workspace.models.target import Target
from target_workspace.models.workspace import Role, User, Workspace

__all__ = [
    "AuditEvent",
    "Board",
    "Column",
    "EventType",
    "PromotionMode",
    "PromotionPolicy",
    "PublisherConfig",
    "Role",
    "SourceConfig",
    "Target",
    "TransitionRule",
    "User",
    "Workspace",
]
