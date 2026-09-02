"""Smoke tests — prove the test infrastructure works.

This file contains two tests:

1. `test_package_import_succeeds` — green from Commit A. Proves the test runner,
   pyproject build system, and import paths are all wired correctly.

2. `test_red_to_be_resolved_in_commit_b` — red from Commit A. Proves that the
   CI pipeline correctly fails on a red test. Commit B removes the deliberate
   failure, demonstrating the TDD red->green->refactor cycle end-to-end on a
   real CI run, on a real commit, against the real foundation.

Do not delete `test_red_to_be_resolved_in_commit_b` from Commit A's tree — it
is load-bearing as the first half of the bootstrap demo.
"""

from __future__ import annotations

import pytest

from target_workspace import __version__


@pytest.mark.fast
def test_package_import_succeeds(workspace_version: str) -> None:
    """The package imports and exposes a version string."""
    assert workspace_version == __version__
    assert isinstance(__version__, str)
    assert __version__.count(".") == 2  # semver MAJOR.MINOR.PATCH


@pytest.mark.fast
def test_red_to_be_resolved_in_commit_b() -> None:
    """The TDD red->green bootstrap demonstration.

    On Commit A this test failed by design (`is_commit_b_green = False`),
    proving the immune system correctly flagged red. On Commit B we flip the
    flag to True, demonstrating red->green on a real CI run against the real
    foundation.

    This is the only test in the project deliberately tied to a commit
    identity. Future tests follow normal TDD discipline: write red, make
    green, refactor.
    """
    is_commit_b_green = True
    assert is_commit_b_green, "Commit B has landed: TDD red->green bootstrap complete."
