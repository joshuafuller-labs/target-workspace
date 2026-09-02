#!/usr/bin/env python3
"""Commit-msg hook: a commit whose message starts with `feat:` or
`fix:` MUST touch at least one test file in the same commit.

The conventional-commits enforcement already requires those prefixes
for behavioural changes; this hook adds the TDD half — if you're
adding behaviour or fixing a bug, the change set must include a
test asserting that behaviour. Catches the "ship now, test next
sprint" pattern that the post-hoc audit was filed against.

Usage:  invoked by pre-commit as a `commit-msg` stage hook.
Args:   $1 is the path to the commit message file.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PREFIXES = ("feat:", "fix:", "feat(", "fix(")


def main(commit_msg_file: str) -> int:
    msg = Path(commit_msg_file).read_text(encoding="utf-8").strip()
    first_line = msg.splitlines()[0] if msg else ""
    if not first_line.startswith(PREFIXES):
        return 0

    # What's staged in this commit. We accept any test file modified or
    # added; CI separately verifies the tests actually exercise the new
    # code (audit/revert_fail_restore.sh) and mutation testing covers
    # the test quality.
    out = subprocess.check_output(
        ["git", "diff", "--cached", "--name-only"],
        text=True,
    )
    staged = [p.strip() for p in out.splitlines() if p.strip()]
    # Polyglot: Python tests live under tests/*.py; the frontend colocates
    # its suite as *.test.ts / *.test.tsx (vitest). A behavioural fix in
    # either tree satisfies the gate when it ships a matching test.
    fe_suffixes = (".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx")
    touched_tests = [
        p
        for p in staged
        if (p.startswith("tests/") and p.endswith(".py")) or p.endswith(fe_suffixes)
    ]
    if touched_tests:
        return 0

    print(
        "TDD gate (check_commit_touches_test): "
        f"commit prefix `{first_line.split(' ', 1)[0]}` indicates a "
        "behavioural change but no test file was touched.",
        file=sys.stderr,
    )
    print(
        "Add or update a test that asserts the new/fixed behaviour. "
        "If you have a real reason to bypass, use --no-verify with a "
        "justification in the commit message.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1]))
