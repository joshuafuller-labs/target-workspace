"""ClassificationScheme plugin contract — workspace-defined handling tag schema.

Defense uses U / CUI / S / TS; LE uses Sensitive / Public / Sealed; SAR may use
none. Workspace owner picks one ClassificationScheme; the rest of the system
treats it as data.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ClassificationScheme(Protocol):
    """A workspace-defined classification or handling-caveat schema."""

    name: str
    """Stable identifier for this scheme, e.g. "dod_us", "le_standard", "none"."""
