"""Single source of truth for the package version.

Read by `target_workspace.__init__`, `pyproject.toml` (via hatchling), and the
healthz endpoint at runtime.
"""

__version__ = "0.1.0"
