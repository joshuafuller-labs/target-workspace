"""Workflow engine — promotion + audit + publish trigger.

Glues together the data layer, the audit log, and the publisher dispatch
on configured column entry. Single code path; PromotionPolicy data drives
the behavior.
"""

from target_workspace.workflow.engine import (
    BoardMovePolicy,
    MoveRequested,
    PolicyDecisionContext,
    PresenceObserved,
    PromotionDenied,
    PromotionResult,
    WorkflowContext,
    WorkflowPolicy,
    apply_decision,
    approve_nomination,
    evaluate,
    evaluate_policy_decisions,
    record_event,
    reduce_decisions,
    reject_nomination,
    transition_target,
)

__all__ = [
    "BoardMovePolicy",
    "MoveRequested",
    "PolicyDecisionContext",
    "PresenceObserved",
    "PromotionDenied",
    "PromotionResult",
    "WorkflowContext",
    "WorkflowPolicy",
    "apply_decision",
    "approve_nomination",
    "evaluate",
    "evaluate_policy_decisions",
    "record_event",
    "reduce_decisions",
    "reject_nomination",
    "transition_target",
]
