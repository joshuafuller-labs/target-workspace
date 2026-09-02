"""mutmut config sanity (tw-7xk).

The bug: mutmut 3.x runs pytest in-process and inherits pyproject's
addopts (--cov=target_workspace --cov-fail-under=85), so every mutant
fails for coverage reasons before the test even reports outcome.

Fix: configure mutmut to invoke pytest with --no-cov so the runner
exercises behavioral correctness, not coverage thresholds.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

try:
    import tomllib  # 3.11+
except ImportError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

pytestmark = [pytest.mark.fast]


def _load_pyproject() -> dict[str, Any]:
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "pyproject.toml"
        if candidate.exists():
            with candidate.open("rb") as fh:
                return tomllib.load(fh)
    msg = "pyproject.toml not found"
    raise RuntimeError(msg)


def test_mutmut_section_present() -> None:
    cfg = _load_pyproject()
    assert "tool" in cfg
    assert "mutmut" in cfg["tool"], "expected [tool.mutmut] section"


def test_mutmut_runner_disables_coverage() -> None:
    cfg = _load_pyproject()
    runner = cfg["tool"]["mutmut"].get("runner", "")
    assert "--no-cov" in runner, (
        f"mutmut runner must disable coverage to avoid the addopts inheritance bug; got: {runner!r}"
    )


def test_mutmut_runner_uses_fast_marker() -> None:
    """Fast marker keeps mutation runs tractable. Without it a full
    integration run for every mutant takes hours."""
    cfg = _load_pyproject()
    runner = cfg["tool"]["mutmut"].get("runner", "")
    assert "-m fast" in runner or "-m 'fast'" in runner, (
        f"mutmut should run only fast tests; got: {runner!r}"
    )
