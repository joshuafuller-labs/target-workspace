"""Smoke check that all plugin Protocols are importable from the public surface.

The plugin contracts are the most stable API in the system; if any of these
imports break, every adapter (first-party and third-party) is affected. This
test runs in the `contract` marker tier and is required to pass on every PR.
"""

from __future__ import annotations

import pytest


@pytest.mark.contract
def test_all_contracts_importable() -> None:
    """Every Protocol declared in the contracts package is importable."""
    from target_workspace.contracts import (
        BoardTemplate,
        ClassificationScheme,
        Effector,
        PromotionPolicy,
        Publisher,
        Source,
        Theme,
    )

    contracts = [
        BoardTemplate,
        ClassificationScheme,
        Effector,
        PromotionPolicy,
        Publisher,
        Source,
        Theme,
    ]

    for contract in contracts:
        assert contract.__name__ != ""
        # Every contract Protocol has a `name` attribute (the adapter's stable id)
        # Verified by introspecting __annotations__ on the Protocol itself.
        assert "name" in contract.__annotations__


@pytest.mark.contract
def test_promotion_policy_contract_is_behavioral() -> None:
    """PromotionPolicy must expose the ADR 0021 decision API, not just a name."""
    from target_workspace.contracts import PromotionPolicy

    assert "evaluate" in PromotionPolicy.__dict__
