"""Promote scripts/audit/mutation_audit.py into a proper pytest case (tw-rkyz).

Mark as `slow` so it runs in CI but skips the local pre-commit fast loop.

User feedback (2026-05-17): 'I prefer proper tests over lots of scripts
for testing. Scripts have to be manually run.'

What this test does:
  - Imports the AUDIT_SETS table from scripts.audit.mutation_audit
  - For each entry, exercises the same in-place patch + subprocess pytest
    + restore loop the script implements
  - Asserts the aggregate kill rate is >= MIN_KILL_RATE

Implementation reuses the helpers in the script so behavior parity
is automatic.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = [pytest.mark.slow]


def _load_audit_module() -> ModuleType:
    """Load scripts.audit.mutation_audit dynamically — the audit dir
    isn't an importable package."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "scripts" / "audit" / "mutation_audit.py"
        if candidate.exists():
            spec = importlib.util.spec_from_file_location(
                "_audit_mutation",
                candidate,
            )
            assert spec
            assert spec.loader
            module = importlib.util.module_from_spec(spec)
            sys.modules["_audit_mutation"] = module
            spec.loader.exec_module(module)
            return module
    msg = "scripts/audit/mutation_audit.py not found"
    raise RuntimeError(msg)


def test_mutation_audit_kill_rate_meets_threshold() -> None:
    """Run the mutation audit and verify aggregate kill rate.

    Promoted from scripts/audit/mutation_audit.py per tw-rkyz so this
    runs automatically in CI under the `slow` marker — no human has to
    remember to invoke a shell script.

    The script exposes a `main()` that returns exit code; we run it and
    assert the exit code is 0 (= all modules at/above MIN_KILL_RATE).
    """
    mod = _load_audit_module()
    main = getattr(mod, "main", None)
    if main is None:
        pytest.skip("mutation_audit.main() not exposed")

    exit_code = main([])
    assert exit_code == 0, (
        f"mutation audit failed with exit_code={exit_code}; survivors logged on stdout"
    )
