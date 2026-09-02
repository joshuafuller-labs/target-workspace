"""Promote scripts/audit/revert_fail_restore.sh into a proper pytest case (tw-rkyz).

Marked `slow` — invokes git checkout on src/ files, runs the target
test, then restores. CI runs this; local fast-loop skips.

For each (test_file, feature_commit) entry: checkout the PARENT of the
feature commit for src/ files that commit touched, run the test file,
and require it to FAIL. A test that still passes against the reverted
impl proves nothing about the feature.

User feedback (2026-05-17): 'I prefer proper tests over lots of scripts
for testing.'
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

pytestmark = [pytest.mark.slow]


REPO = Path(__file__).resolve().parents[2]


# Mirror of the AUDIT list in scripts/audit/revert_fail_restore.sh.
# Keep in sync; if the script's list grows, this should too.
AUDIT: list[tuple[str, str]] = [
    ("tests/integration/test_reorder.py", "3f4c308"),
    ("tests/integration/test_alembic_migrations.py", "51d1ef0"),
    ("tests/integration/test_track_correlation.py", "ac1adf5"),
    ("tests/integration/test_rbac.py", "3530620"),
    ("tests/unit/test_publishers_tak_server.py", "5506b71"),
]


def _git_files_touched(commit: str) -> list[str]:
    """Return src/ file paths touched by the given commit."""
    out = subprocess.check_output(
        ["git", "-C", str(REPO), "show", "--name-only", "--pretty=format:", commit],
        text=True,
    )
    return [
        line.strip()
        for line in out.splitlines()
        if line.strip() and line.strip().startswith("src/")
    ]


def _commit_exists(commit: str) -> bool:
    return (
        subprocess.run(
            ["git", "-C", str(REPO), "rev-parse", "--verify", commit],
            check=False,
            capture_output=True,
        ).returncode
        == 0
    )


def _path_exists_at_ref(ref: str, path: str) -> bool:
    return (
        subprocess.run(
            ["git", "-C", str(REPO), "cat-file", "-e", f"{ref}:{path}"],
            check=False,
            capture_output=True,
        ).returncode
        == 0
    )


def _restore_path_from_parent(parent: str, path: str) -> None:
    if _path_exists_at_ref(parent, path):
        body = subprocess.check_output(
            ["git", "-C", str(REPO), "show", f"{parent}:{path}"],
        )
        (REPO / path).write_bytes(body)
        return

    current = REPO / path
    if current.exists():
        current.unlink()


def _assert_test_fails_against_reverted_impl(
    test_file: str,
    feature_commit: str,
) -> None:
    """For each (test, feature_commit): revert src/ to PARENT(commit),
    run test, assert it FAILS, then restore."""
    if not _commit_exists(feature_commit):
        pytest.skip(f"commit {feature_commit} not in this clone")

    touched = _git_files_touched(feature_commit)
    if not touched:
        pytest.skip(f"commit {feature_commit} touched no src/ files")

    test_path = REPO / test_file
    if not test_path.exists():
        pytest.skip(f"{test_file} no longer present")

    parent = f"{feature_commit}^"

    # Back up each touched file by copying its CURRENT content aside.
    backups: dict[str, bytes] = {}
    for f in touched:
        p = REPO / f
        if p.exists():
            backups[f] = p.read_bytes()

    try:
        # Revert each touched file to PARENT(commit).
        for f in touched:
            _restore_path_from_parent(parent, f)
        # Run the target test. Expect failure.
        result = subprocess.run(
            ["uv", "run", "pytest", test_file, "--no-cov", "-x", "-q"],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=300,
        )
        assert result.returncode != 0, (
            f"{test_file} STILL PASSES against {parent} for "
            f"commit {feature_commit} — the test is bogus and must be "
            f"rewritten with proper red-then-green TDD.\n"
            f"stdout:\n{result.stdout[-2000:]}"
        )
    finally:
        # Restore the original bytes regardless of outcome.
        for f, body in backups.items():
            (REPO / f).write_bytes(body)


def test_tests_fail_against_reverted_impls() -> None:
    for test_file, feature_commit in AUDIT:
        _assert_test_fails_against_reverted_impl(test_file, feature_commit)
