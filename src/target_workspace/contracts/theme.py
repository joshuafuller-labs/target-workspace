"""Theme plugin contract — UI palette, typography, iconography per workspace.

The four flagship mockups (DoD tactical, DoD operational, federal LE, SAR) are
example Themes, not products. A workspace owner picks one or writes their own.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class Theme(Protocol):
    """A workspace UI theme: palette, typography, iconography."""

    name: str
    """Stable identifier for this theme, e.g. "tactical", "federal", "sar", "neutral"."""
