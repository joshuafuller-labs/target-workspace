"""Demo capability — seed scenarios that hydrate a populated workspace.

Per ADR 0010: demo is the first post-MVP feature. Scenarios are portable
YAML files importable via the same code path workspaces use to bootstrap
themselves. The architectural enablers (injectable clock, source-provided
timestamps, target_workspace.demos entry-points group) live in MVP so
post-MVP demo work is cheap.
"""

from target_workspace.demo.loader import (
    ScenarioNotFoundError,
    discover_scenarios,
    load_scenario,
    seed_workspace,
)

__all__ = [
    "ScenarioNotFoundError",
    "discover_scenarios",
    "load_scenario",
    "seed_workspace",
]
