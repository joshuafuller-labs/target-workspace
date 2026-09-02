# Target Workspace — developer command wrappers
# Run `just` (no args) to list recipes.

set shell := ["bash", "-c"]
set dotenv-load := true

# Show available recipes
default:
    @just --list

# Install all dependencies (project + dev) into the local venv
sync:
    uv sync --all-extras --dev

# Boot the API with hot-reload (local dev)
dev:
    uv run uvicorn target_workspace.api.app:app --reload --host 127.0.0.1 --port 8000

# Boot the frontend dev server (Vite)
fe:
    cd frontend && npm run dev

# Run the full test suite (parallel)
test:
    uv run pytest -n auto

# Run only the fast unit subset (what pre-commit runs)
test-fast:
    uv run pytest -n auto -m fast

# Watch mode — re-runs tests on save (TDD inner loop)
watch:
    uv run pytest-watcher . --runner pytest -m fast

# Run every gate that CI runs, in the order CI runs them
check:
    bash scripts/check.sh

# Lint + format check (does not write)
lint:
    uv run ruff check .
    uv run ruff format --check .

# Auto-fix lint and format
fix:
    uv run ruff check . --fix
    uv run ruff format .

# Type-check
typecheck:
    uv run mypy src tests

# Security scans (advisory + license)
audit:
    uv run pip-audit --strict
    uv run pip-licenses --format=json --with-license-file \
        --fail-on="GPL-2.0;GPL-3.0;AGPL-3.0;SSPL"

# Build container image (local; not pushed)
build:
    docker buildx build --load -t target-workspace:dev -f docker/Dockerfile .

# Generate / refresh uv lockfile
lock:
    uv lock

# Upgrade locked deps to latest matching constraints (curated; CI gates the PR)
lock-upgrade:
    uv lock --upgrade

# Generate SBOM for current env (CycloneDX)
sbom:
    docker run --rm -v "$(pwd):/work" anchore/syft:v1.44.0 \
        dir:/work -o cyclonedx-json=sbom.cyclonedx.json

# Clean build / cache artifacts
clean:
    rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage coverage.xml htmlcov dist build
    find . -type d -name __pycache__ -exec rm -rf {} +
