# ADR 0005 — Plugin discovery via `importlib.metadata.entry_points`

**Status:** Accepted
**Date:** 2026-05-16

## Context

The malleability principle ([ADR 0008](0008-malleability-principle.md)) makes pluggability the product's load-bearing feature. Source, Publisher, Effector, and PromotionPolicy are public plugin families today because they have loader support and contract tests. ClassificationScheme, Theme, and BoardTemplate remain reserved families: they are design direction, not an advertised third-party surface, until loader support and conformance tests make them load-bearing.

## Decision

Plugin discovery uses Python's stdlib `importlib.metadata.entry_points()` via declared entry-point groups:
- `target_workspace.sources`
- `target_workspace.publishers`
- `target_workspace.effectors`
- `target_workspace.policies`

Reserved entry-point groups, not public until implemented and contract-tested:
- `target_workspace.classifications`
- `target_workspace.themes`
- `target_workspace.boards`

First-party adapters live in `src/target_workspace/plugins/` and register through the project's own `pyproject.toml`. Third-party adapters are installable via `uv pip install target-workspace-source-mqtt` (or any other naming convention) and become discoverable without core changes.

Each public Protocol contract (in `src/target_workspace/contracts/`) has a corresponding conformance-test harness in `tests/contract/` that any implementation can be validated against. A contract becomes public only when the loader discovers it and the tests assert behavioral methods, not just importability.

## Consequences

**Wins:**
- Production-grade discovery — same mechanism used by `pytest`, `mkdocs`, `pre-commit`, `pip`, every mature Python plugin ecosystem
- Zero invented infrastructure
- `pip install` is the install model — no plugin marketplace needed for MVP
- Conformance tests give plugin authors deterministic feedback before publishing

**Trade-offs accepted:**
- Locks the project to Python's plugin model — but we're already Python-only per [ADR 0002](0002-python-fastapi-stack.md)
- Plugin authors must publish to PyPI or a private index; can't drag-and-drop a `.py` file into a config dir
- Process boundary is in-process; a misbehaving plugin can crash the workspace. **Mitigation:** plugins validated by conformance tests before listing; future post-MVP enhancement to load plugins in subprocess or WASM (Extism) if isolation becomes a concern

## References

- https://packaging.python.org/en/latest/specifications/entry-points/
- https://docs.python.org/3/library/importlib.metadata.html#entry-points
