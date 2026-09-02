#!/usr/bin/env bash
# Run every gate that CI runs, in the order CI runs them.
# Mirrors .github/workflows/pr.yml — keep them aligned.
set -euo pipefail

echo "== sync deps =="
uv sync --all-extras --dev

echo "== ruff (lint) =="
uv run ruff check .

echo "== ruff (format) =="
uv run ruff format --check .

echo "== mypy --strict =="
uv run mypy src tests

echo "== bandit =="
uv run bandit -r src -c pyproject.toml

echo "== detect-secrets =="
if [ -f .secrets.baseline ]; then
    uv run detect-secrets scan --baseline .secrets.baseline
else
    echo "  (no .secrets.baseline yet — generated in Commit B)"
fi

echo "== pytest (parallel + coverage) =="
uv run pytest -n auto --cov-fail-under=90 || {
    echo
    echo "NOTE: 'test_red_to_be_resolved_in_commit_b' fails by design on Commit A."
    echo "      This script returns non-zero until Commit B flips it green."
    exit 1
}

echo "== pip-audit =="
# Audit RUNTIME deps only (--no-dev), excluding our own (unpublished) package.
# Mirrors pr.yml exactly (tw-qvdi.12): without --no-dev the export pulls dev
# tooling like pip (via pip-audit/pip-api), whose advisories aren't shipped and
# would fail the local gate while CI stays green.
uv export --no-dev --no-emit-project --no-hashes --format requirements-txt 2>/dev/null \
    | uv run pip-audit --strict --requirement /dev/stdin

echo "== pip-licenses (allow-list) =="
uv run pip-licenses --format=json --with-license-file \
    --fail-on="GPL-2.0;GPL-3.0;AGPL-3.0;SSPL;UNKNOWN"

echo
echo "All gates green."
