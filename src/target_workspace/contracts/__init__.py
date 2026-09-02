"""Plugin contracts - the public API surface for adapters.

First-party adapters in `target_workspace.plugins` implement these; third-party
adapters installed via `uv pip install <pkg>` register through
`importlib.metadata.entry_points` and are discovered without core changes.

Per the malleability principle (docs/adr/0008): the core is rigorously general,
the defaults are opinionated, and the community owns the templates and themes.
"""

from target_workspace.contracts.board_template import BoardTemplate
from target_workspace.contracts.classification import ClassificationScheme
from target_workspace.contracts.effector import Effector
from target_workspace.contracts.promotion_policy import PromotionPolicy
from target_workspace.contracts.publisher import Publisher
from target_workspace.contracts.source import Source
from target_workspace.contracts.theme import Theme

__all__ = [
    "BoardTemplate",
    "ClassificationScheme",
    "Effector",
    "PromotionPolicy",
    "Publisher",
    "Source",
    "Theme",
]
