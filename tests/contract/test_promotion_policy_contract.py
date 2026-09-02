"""PromotionPolicy contract tests for ADR 0021's decision API."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from target_workspace.contracts.promotion_policy import (
    Decision,
    DecisionContext,
    PromotionPolicy,
    Signal,
)

pytestmark = [pytest.mark.contract]


class AbstainingPolicy:
    name = "abstaining"

    def evaluate(self, signal: Signal, ctx: DecisionContext) -> Decision:
        assert signal.kind == "external:test.noop"
        assert ctx.board_id is None
        return Decision.abstain(
            reason="not relevant",
            proposed_by=signal.emitted_by,
            target_id=signal.target_id,
        )


def test_policy_evaluate_returns_decision() -> None:
    signal = Signal(
        kind="external:test.noop",
        emitted_by="policy:test",
        target_id=uuid4(),
        occurred_at=datetime(2026, 6, 4, tzinfo=UTC),
        payload={"confidence": 0.42},
    )
    context = DecisionContext(board_id=None)

    policy: PromotionPolicy = AbstainingPolicy()
    decision = policy.evaluate(signal, context)

    assert isinstance(policy, PromotionPolicy)
    assert decision.verdict == "abstain"
    assert decision.reason == "not relevant"
    assert decision.proposed_by == "policy:test"
    assert decision.evidence == {}


def test_propose_decision_requires_approver_role() -> None:
    with pytest.raises(ValueError, match="approver_role"):
        Decision.propose(reason="needs review", proposed_by="policy:test")


def test_external_signal_namespace_is_validated() -> None:
    with pytest.raises(ValueError, match="external signal"):
        Signal(
            kind="external:",
            emitted_by="source:test",
            occurred_at=datetime(2026, 6, 4, tzinfo=UTC),
        )
