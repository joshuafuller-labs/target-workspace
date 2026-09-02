from __future__ import annotations

import importlib.util

import pytest

pytestmark = [pytest.mark.fast]


def test_postgres_runtime_driver_is_packaged() -> None:
    """Postgres deployments need psycopg in the production image, not just tests."""
    assert importlib.util.find_spec("psycopg") is not None
