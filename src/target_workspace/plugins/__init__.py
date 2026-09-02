"""First-party + community plugin loading.

Per ADR 0005, public plugin discovery uses Python's stdlib
`importlib.metadata.entry_points` via the groups:
  - target_workspace.sources
  - target_workspace.publishers
  - target_workspace.effectors
  - target_workspace.policies

Adapters install via `uv pip install <pkg>` and are discovered without core
changes. First-party adapters live in this package.
"""

from target_workspace.plugins.loader import (
    discover_effectors,
    discover_policies,
    discover_publishers,
    discover_sources,
    register_builtin_plugins,
)

__all__ = [
    "discover_effectors",
    "discover_policies",
    "discover_publishers",
    "discover_sources",
    "register_builtin_plugins",
]
