"""Compatibility exports for presence workflow trigger policy.

The pure trigger evaluator lives in ``target_workspace.workflow.triggers``.
This module remains so existing API-side imports do not churn.
"""

from target_workspace.workflow.triggers import (
    PresenceWorkflowPolicy,
    WorkflowTriggerRule,
    consider_actions,
    presence_decisions,
)

__all__ = [
    "PresenceWorkflowPolicy",
    "WorkflowTriggerRule",
    "consider_actions",
    "presence_decisions",
]
