#!/usr/bin/env python3
"""Pre-commit gate: a new module added under src/ must ship with a
matching test file in the same commit.

"Matching" means: for src/<pkg>/<module>.py we expect at least one of
  tests/unit/test_<module>.py
  tests/integration/test_<module>.py
  tests/contract/test_<module>.py
  tests/<anywhere>/test_<module>*.py

Catches the TDD violation pattern of "ship the feature, write the
tests next week." Blocks the commit; user must add a test (or use
--no-verify if there's a justification that survives review).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def staged_paths() -> list[Path]:
    out = subprocess.check_output(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=A"],
        cwd=REPO,
        text=True,
    )
    return [Path(p.strip()) for p in out.splitlines() if p.strip()]


def main() -> int:
    added = staged_paths()
    # New python modules under src/ excluding __init__.py and migrations
    # (migrations have their own audit path).
    new_src_modules = [
        p
        for p in added
        if p.parts[0] == "src"
        and p.suffix == ".py"
        and p.name != "__init__.py"
        and "migrations" not in p.parts
    ]
    if not new_src_modules:
        return 0

    # Any test file added in this commit (anywhere under tests/)
    test_files = {p for p in added if p.parts[0] == "tests" and p.suffix == ".py"}
    # Also accept test files modified in this commit (extending an
    # existing suite for the new module is fine).
    out = subprocess.check_output(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=M"],
        cwd=REPO,
        text=True,
    )
    test_files.update(
        Path(p.strip())
        for p in out.splitlines()
        if p.strip().startswith("tests/") and p.strip().endswith(".py")
    )

    missing: list[Path] = []
    for module in new_src_modules:
        stem = module.stem
        # Tolerant match: test file mentions the module stem.
        pattern = re.compile(rf"test_{re.escape(stem)}(_|\.py$|$)")
        if not any(pattern.search(str(t)) for t in test_files):
            missing.append(module)

    if not missing:
        return 0

    print(
        "TDD gate (check_new_module_has_test): "
        "new src/ modules without a matching test file in the same commit:",
        file=sys.stderr,
    )
    for m in missing:
        print(f"  - {m}  (expected something like tests/**/test_{m.stem}*.py)", file=sys.stderr)
    print(
        "\nWrite the failing test FIRST. If you have a real reason to bypass, "
        "use --no-verify with a justification in the commit message.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
