"""BoardTemplate plugin contract — pre-built board column sets and transition rules.

Bundled templates include F3EAD, D3A, JP 3-60 Joint Targeting, F2T2EA, LE case,
SAR mission. A workspace owner picks one as the starting point and customizes.

These are explicitly *example templates*, not core code, per the malleability
principle (docs/adr/0008).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class BoardTemplate(Protocol):
    """A bundled board template: ordered columns, transition rules, default policy."""

    name: str
    """Stable identifier, e.g. "f3ead", "d3a", "le_case", "sar_mission"."""
