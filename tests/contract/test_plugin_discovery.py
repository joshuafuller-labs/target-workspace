"""Plugin discovery + conformance harness tests (TDD chunk 8b)."""

from __future__ import annotations

import pytest

from target_workspace.contracts.effector import Effector
from target_workspace.contracts.promotion_policy import (
    Decision,
    DecisionContext,
    PromotionPolicy,
    Signal,
)
from target_workspace.contracts.publisher import Publisher
from target_workspace.contracts.source import Source
from target_workspace.plugins.loader import (
    discover_effectors,
    discover_policies,
    discover_publishers,
    discover_sources,
    register_builtin_plugins,
    register_policy,
)

pytestmark = [pytest.mark.contract]


def test_builtin_source_plugins_registered() -> None:
    register_builtin_plugins()
    sources = discover_sources()
    assert "manual" in sources


def test_builtin_publisher_plugins_registered() -> None:
    register_builtin_plugins()
    publishers = discover_publishers()
    assert "raw_cot" in publishers
    assert "webhook_out" in publishers


def test_builtin_effector_plugins_registered() -> None:
    register_builtin_plugins()
    effectors = discover_effectors()
    assert "manual_effector" in effectors


def test_policy_plugins_can_register_and_discover() -> None:
    class AlwaysAllowPolicy:
        name = "always_allow"

        def evaluate(self, signal: Signal, ctx: DecisionContext) -> Decision:
            _ = (signal, ctx)
            return Decision.allow(reason="test", proposed_by="policy:test")

    register_policy(AlwaysAllowPolicy.name, AlwaysAllowPolicy)

    policies = discover_policies()
    assert policies["always_allow"] is AlwaysAllowPolicy
    assert isinstance(policies["always_allow"](), PromotionPolicy)


def test_source_plugins_conform_to_protocol() -> None:
    """Every registered Source plugin satisfies the runtime-checkable Protocol."""
    register_builtin_plugins()
    for name, cls in discover_sources().items():
        instance = cls()
        assert isinstance(instance, Source), f"{name} does not satisfy Source Protocol"


def test_publisher_plugins_conform_to_protocol() -> None:
    """Every registered Publisher plugin satisfies the runtime-checkable Protocol."""
    register_builtin_plugins()
    for name, cls in discover_publishers().items():
        instance = cls()
        assert isinstance(instance, Publisher), f"{name} does not satisfy Publisher Protocol"


def test_effector_plugins_conform_to_protocol() -> None:
    """Every registered Effector plugin satisfies the runtime-checkable Protocol."""
    register_builtin_plugins()
    for name, cls in discover_effectors().items():
        instance = cls()
        assert isinstance(instance, Effector), f"{name} does not satisfy Effector Protocol"
