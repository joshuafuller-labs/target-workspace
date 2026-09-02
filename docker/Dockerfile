# syntax=docker/dockerfile:1.7
#
# Target Workspace — multi-stage container build.
#
# Layout:
#   Stage 1: frontend-build (Node)  — npm ci, copy Cesium assets, vite build
#   Stage 2: builder (Python slim) — pip install into /opt/venv
#   Stage 3: runtime (Python slim) — venv + Python src + built SPA
#
# The Python slim digest is pinned to 3.14.5-slim-trixie. It is intentionally
# used for both builder and runtime because the ARC runner CPU cannot execute
# the current Chainguard Python/uv binaries (x86-64-v2 baseline).
ARG PYTHON_SLIM_DIGEST=sha256:c845af9399020c7e562969a13689e929074a10fd057acd1b1fad06a2fb068e97
ARG SQLITE_AUTOCONF_VERSION=3500200

# ---------------------------------------------------------------------------
# Stage 0: SQLite security floor
# ---------------------------------------------------------------------------
FROM python:3.14-slim@${PYTHON_SLIM_DIGEST} AS sqlite-build
ARG SQLITE_AUTOCONF_VERSION

ADD https://www.sqlite.org/2025/sqlite-autoconf-${SQLITE_AUTOCONF_VERSION}.tar.gz /tmp/sqlite.tar.gz
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential ca-certificates \
    && tar -xzf /tmp/sqlite.tar.gz -C /tmp \
    && cd /tmp/sqlite-autoconf-${SQLITE_AUTOCONF_VERSION} \
    && ./configure --prefix=/usr/local --disable-static \
    && make -j"$(nproc)" \
    && make install

# ---------------------------------------------------------------------------
# Stage 1: frontend build
# Vite builds the SPA into frontend/dist. The vite-plugin-cesium plugin copies
# Cesium's static assets (Workers/, Assets/, ThirdParty/, Widgets/) into
# dist/cesium during the build, so we end up with a self-contained dist/ that
# FastAPI mounts at the SPA root.
# ---------------------------------------------------------------------------
# Base image digest-pinned (node:24-alpine as of 2026-05-23); Dependabot's docker
# ecosystem maintains the digest under the 5-day cooldown.
FROM node:26-alpine@sha256:2d984a15c9b54fd0aeb608b8e0d0d83529eb34d2966db27a1fb4f1edc3d298a3 AS frontend-build

WORKDIR /frontend

# Package metadata first — cache the install layer when only sources change.
# `npm install` (not `npm ci`) is used because Vite/Rolldown pull in
# platform-specific optional native deps (@emnapi/core, etc.); the lockfile
# generated on the host doesn't list every per-arch variant, and `npm ci`
# refuses to reconcile. `npm install` is tolerant.
# .npmrc carries `ignore-scripts=true` — blocks dependency install scripts (the
# npm-worm execution vector) during the image build too, not just in CI.
COPY frontend/package.json frontend/package-lock.json* frontend/.npmrc ./
RUN npm install --no-audit --no-fund --include=optional

# Now the rest of the frontend tree
COPY frontend/ ./

# Build: runs prebuild (cesium asset copy) then tsc + vite build.
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2: Python builder
# ---------------------------------------------------------------------------
FROM python:3.14-slim@${PYTHON_SLIM_DIGEST} AS builder

USER root
WORKDIR /build

# Project metadata first for layer caching. README.md is referenced from
# pyproject.toml (readme = "README.md") and hatchling reads it during
# wheel build, so it must be present.
COPY pyproject.toml uv.lock* README.md ./
COPY src ./src

# Resolve + install into a venv at /opt/venv
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir .

# Pre-create the data dir with nonroot ownership so the named volume in
# compose inherits writable permissions when first mounted. The runtime
# stage runs as a numeric nonroot user.
RUN mkdir -p /staging/data && chown -R 65532:65532 /staging/data

# ---------------------------------------------------------------------------
# Stage 3: runtime
# ---------------------------------------------------------------------------
FROM python:3.14-slim@${PYTHON_SLIM_DIGEST} AS runtime

WORKDIR /app
RUN mkdir -p /app /data && chown -R 65532:65532 /app /data

# Python's _sqlite3 extension links dynamically. Override Debian's older
# libsqlite3 with the patched floor required by scripts/verify_sqlite.py.
COPY --from=sqlite-build /usr/local/lib/libsqlite3.so /usr/local/lib/libsqlite3.so
COPY --from=sqlite-build /usr/local/lib/libsqlite3.so.0 /usr/local/lib/libsqlite3.so.0
COPY --from=sqlite-build /usr/local/lib/libsqlite3.so.3.50.2 /usr/local/lib/libsqlite3.so.3.50.2
ENV LD_LIBRARY_PATH=/usr/local/lib

# Copy the resolved venv only (no build artifacts)
COPY --from=builder --chown=65532:65532 /opt/venv /opt/venv

# /data is the SQLite mount point per docker-compose. Pre-stage with
# nonroot ownership so the named volume inherits the writable
# permissions on first mount.
COPY --from=builder --chown=65532:65532 /staging/data /data

# Copy app source (already built into the venv as a wheel)
COPY --chown=65532:65532 src ./src
COPY --chown=65532:65532 scripts/verify_sqlite.py /app/scripts/verify_sqlite.py
# Alembic migrations + config — runs at boot via _run_alembic_upgrade in
# api/app.py. Resolved relative to __file__ → parents[3] (/app).
COPY --chown=65532:65532 alembic.ini /app/alembic.ini
COPY --chown=65532:65532 migrations /app/migrations

# Copy the built SPA. `src/target_workspace/api/app.py:_mount_spa` resolves
# `parents[3]` of __file__ inside the container — `/app/` — and looks for
# `frontend/dist/`. Place the build at that path so the FastAPI app serves
# `/`, `/assets/*`, and the Cesium runtime assets at `/cesium/*`.
COPY --from=frontend-build --chown=65532:65532 /frontend/dist /app/frontend/dist

# SQLite version gate — fail the image build if bundled sqlite < 3.50.2
RUN ["/opt/venv/bin/python", "/app/scripts/verify_sqlite.py"]

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UVICORN_HOST=0.0.0.0 \
    UVICORN_PORT=8000 \
    # uv installs the project editably by default. The editable .pth file
    # points at the build-stage path (/build/src) which doesn't exist in
    # runtime, so we override with the actual runtime src path.
    PYTHONPATH=/app/src

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).read()"]

# OCI labels
LABEL org.opencontainers.image.title="target-workspace" \
      org.opencontainers.image.description="Configurable kanban for the target lifecycle. CoT-native, plugin-driven." \
      org.opencontainers.image.source="https://github.com/joshuafuller-labs/target-workspace" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.base.name="python:3.14-slim" \
      org.opencontainers.image.base.digest="${PYTHON_SLIM_DIGEST}"

USER 65532:65532
ENTRYPOINT ["python", "-m", "uvicorn", "--factory", "target_workspace.api.app:create_app"]
