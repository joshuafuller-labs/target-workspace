"""Password hashing cost controls."""

from __future__ import annotations

import pytest

from target_workspace.api.auth import bcrypt_rounds_for_env, hash_password, verify_password
from target_workspace.api.config import secure_cookies_for_env

pytestmark = [pytest.mark.fast]


def test_test_env_can_lower_bcrypt_rounds() -> None:
    assert bcrypt_rounds_for_env(env="test", requested_rounds=4) == 4

    hashed = hash_password("pw", env="test", bcrypt_rounds=4)

    assert hashed.startswith("$2b$04$")
    assert verify_password("pw", hashed)


def test_non_test_env_keeps_bcrypt_rounds_at_least_default() -> None:
    assert bcrypt_rounds_for_env(env="dev", requested_rounds=4) >= 12
    assert bcrypt_rounds_for_env(env="prod", requested_rounds=4) >= 12


def test_test_env_uses_non_secure_cookies_for_http_test_client() -> None:
    assert secure_cookies_for_env("dev") is False
    assert secure_cookies_for_env("test") is False
    assert secure_cookies_for_env("staging") is True
    assert secure_cookies_for_env("prod") is True
