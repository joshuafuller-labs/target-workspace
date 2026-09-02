#!/usr/bin/env bash
# Boot the dev stack: API on :8000, frontend on :5173.
# Hot reload on both.
set -euo pipefail

trap 'kill 0' EXIT

echo "== installing deps =="
uv sync --all-extras --dev
( cd frontend && npm install )

echo "== starting backend (uvicorn) on :8000 =="
uv run uvicorn --factory target_workspace.api.app:create_app --reload --host 127.0.0.1 --port 8000 &

echo "== starting frontend (vite) on :5173 =="
( cd frontend && npm run dev ) &

wait
