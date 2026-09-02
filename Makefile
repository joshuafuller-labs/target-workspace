# Target Workspace — top-level make targets.

.PHONY: audit audit-revert audit-mutation test test-fast lint typecheck install-hooks

# Single-command TDD trust audit. Per the goal-state agreed 2026-05-17:
#   1. Each post-hoc test legitimately fails against reverted impl
#      (otherwise it proves nothing about the feature).
#   2. Mutation kill rate >= 80% on audited modules.
audit: audit-revert audit-mutation

audit-revert:
	@echo
	@echo "═══════ Step 1: revert/fail/restore ═══════"
	@scripts/audit/revert_fail_restore.sh

audit-mutation:
	@echo
	@echo "═══════ Step 2: mutation audit ═══════"
	@scripts/audit/mutation_audit.py

test:
	.venv/bin/python -m pytest

test-fast:
	.venv/bin/python -m pytest -m fast --no-cov -x

test-e2e:
	cd frontend && npx playwright test

install-hooks:
	.venv/bin/pre-commit install --install-hooks
