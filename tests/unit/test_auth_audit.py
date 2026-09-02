"""Unit coverage for shared auth audit helpers."""

from __future__ import annotations

import pytest

from target_workspace.api.auth_audit import ua_family

pytestmark = [pytest.mark.fast]


@pytest.mark.parametrize(
    ("user_agent", "expected"),
    [
        ("Mozilla/5.0 Firefox/150.0", "firefox"),
        ("Mozilla/5.0 AppleWebKit/537.36 Chrome/148.0", "chrome"),
        ("node", "node"),
        ("", "unknown"),
    ],
)
def test_ua_family_extracts_coarse_browser_family(user_agent: str, expected: str) -> None:
    assert ua_family(user_agent) == expected
