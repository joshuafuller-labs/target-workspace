from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = ROOT / "docker" / "Dockerfile"


def test_dockerfile_does_not_copy_uv_from_official_image() -> None:
    dockerfile = DOCKERFILE.read_text()

    assert "COPY --from=ghcr.io/astral-sh/uv" not in dockerfile
    assert "ghcr.io/astral-sh/uv:0.11.14" not in dockerfile
    assert "uv --version" not in dockerfile
    assert "UV_VERSION" not in dockerfile


def test_dockerfile_uses_cpu_baseline_python_slim_builder() -> None:
    dockerfile = DOCKERFILE.read_text()

    assert "PYTHON_SLIM_DIGEST" in dockerfile
    assert "FROM python:3.14-slim@${PYTHON_SLIM_DIGEST} AS builder" in dockerfile
    assert "FROM python:3.14-slim@${PYTHON_SLIM_DIGEST} AS runtime" in dockerfile
    assert "python -m venv /opt/venv" in dockerfile
    assert "/opt/venv/bin/pip install --no-cache-dir ." in dockerfile


def test_dockerfile_supplies_sqlite_security_floor() -> None:
    dockerfile = DOCKERFILE.read_text()

    assert "SQLITE_AUTOCONF_VERSION=3500200" in dockerfile
    assert "FROM python:3.14-slim@${PYTHON_SLIM_DIGEST} AS sqlite-build" in dockerfile
    assert "COPY --from=sqlite-build /usr/local/lib/libsqlite3.so" in dockerfile
    assert "COPY --from=sqlite-build /usr/local/lib/libsqlite3.so.3.50.2" in dockerfile
    assert "LD_LIBRARY_PATH=/usr/local/lib" in dockerfile
    assert 'RUN ["/opt/venv/bin/python", "/app/scripts/verify_sqlite.py"]' in dockerfile
