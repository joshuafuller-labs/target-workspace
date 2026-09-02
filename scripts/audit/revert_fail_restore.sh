#!/usr/bin/env bash
# revert_fail_restore.sh — TDD post-hoc audit.
#
# For each (test_file, feature_commit) pair: checkout the PARENT of the
# feature commit for all src/ files that commit touched, run the test
# file, and require it to FAIL. A test that still passes against the
# reverted impl is worthless (proves nothing about the feature) and must
# be deleted + rewritten with proper red-then-green TDD.
#
# When done, restore HEAD's src/ files. Report per-test PASS/FAIL/ERROR
# and total verdict.
#
# Usage:  ./scripts/audit/revert_fail_restore.sh
# Exit:   0 if every audited test FAILED against reverted impl (good),
#         1 if any test PASSED against reverted impl (test is bogus).

set -u

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$REPO_ROOT"

# Each entry: TEST_FILE@FEATURE_COMMIT
AUDIT=(
  "tests/integration/test_reorder.py@3f4c308"
  "tests/integration/test_alembic_migrations.py@51d1ef0"
  "tests/integration/test_track_correlation.py@ac1adf5"
  "tests/integration/test_rbac.py@3530620"
  "tests/unit/test_publishers_tak_server.py@5506b71"
)

PYTEST="${PYTEST:-.venv/bin/python3 -m pytest}"

# SAFETY: this script does `git checkout HEAD -- <src>` to revert
# tracked files for each audit. If you have UNCOMMITTED changes to
# those files, they'd be silently destroyed. Stash everything up-front
# and pop on exit so the audit can never eat your work.
STASHED=0
if [ -n "$(git status --porcelain)" ]; then
  git stash push -u -m "revert_fail_restore.sh auto-stash" >/dev/null
  STASHED=1
  echo "auto-stashed uncommitted changes; will restore on exit"
  trap 'if [ "$STASHED" = "1" ]; then git stash pop >/dev/null && echo "uncommitted changes restored"; fi' EXIT
fi

# Track results: passing-against-reverted = BOGUS, failing-against-
# reverted = LEGITIMATE.
BOGUS=()
LEGIT=()

revert_src_for() {
  local commit="$1"
  # All src/ files modified or added in the feature commit. Migrations
  # in migrations/versions/ also need to revert so alembic doesn't
  # exercise the new schema.
  git diff-tree --no-commit-id --name-only -r "$commit" \
    | grep -E '^(src/|migrations/versions/)'
}

run_one() {
  local test_file="$1"
  local commit="$2"
  echo
  echo "════════════════════════════════════════════════════════════════"
  echo "AUDIT: $test_file"
  echo "  feature commit: $commit"
  echo "  parent: $(git rev-parse "${commit}^")"
  echo

  # Files to revert (and to keep, since the test itself must survive)
  mapfile -t src_files < <(revert_src_for "$commit")
  if [ "${#src_files[@]}" -eq 0 ]; then
    echo "  no src/ files in commit; skipping"
    return 0
  fi

  # Snapshot HEAD state, then check out parent versions.
  echo "  reverting:"
  printf '    - %s\n' "${src_files[@]}"
  for f in "${src_files[@]}"; do
    if git cat-file -e "${commit}^:${f}" 2>/dev/null; then
      git show "${commit}^:${f}" > "$f"
    else
      # File didn't exist in parent — delete it locally for this run.
      rm -f "$f"
    fi
  done

  # Run the test with a json report so we can verdict per-test, not
  # per-file. A single passing test inside a mostly-failing file is
  # still bogus — it proves the test doesn't depend on the feature.
  local report="/tmp/tw-audit-$(basename "$test_file" .py).json"
  rm -f "$report"
  set +e
  out=$($PYTEST "$test_file" -v --no-cov --tb=line \
    --json-report --json-report-file="$report" 2>&1)
  rc=$?
  set -e

  # Restore HEAD state BEFORE analyzing — so a script crash doesn't
  # leave the repo dirty.
  git checkout HEAD -- "${src_files[@]}" 2>/dev/null || true

  if [ ! -f "$report" ]; then
    # pytest-json-report wasn't installed or collection error left no
    # report. Fall back to a single bucket verdict by exit code.
    if [ "$rc" -ne 0 ]; then
      LEGIT+=("$test_file (collection error / no report)")
      echo "  ✓ LEGITIMATE (no per-test breakdown — collection failed)"
    else
      BOGUS+=("$test_file (no report, passed)")
      echo "  ✗ BOGUS — file passed against reverted impl"
    fi
    return 0
  fi

  # Walk the json report and bucket per-test.
  local jq_out
  jq_out=$(python3 -c "
import json, sys
data = json.load(open(sys.argv[1]))
for t in data.get('tests', []):
    print(f\"{t['outcome']}\\t{t['nodeid']}\")
" "$report")
  echo "  per-test:"
  while IFS=$'\t' read -r outcome nodeid; do
    [ -z "$nodeid" ] && continue
    if [ "$outcome" = "passed" ]; then
      BOGUS+=("$nodeid")
      echo "    ✗ BOGUS — $nodeid (passed against reverted impl)"
    else
      LEGIT+=("$nodeid")
      echo "    ✓ legit  — $nodeid ($outcome)"
    fi
  done <<< "$jq_out"
}

for entry in "${AUDIT[@]}"; do
  test_file="${entry%@*}"
  commit="${entry##*@}"
  run_one "$test_file" "$commit"
done

echo
echo "════════════════════════════════════════════════════════════════"
echo "SUMMARY"
echo "  legitimate (failed against reverted impl): ${#LEGIT[@]}"
for f in "${LEGIT[@]}"; do echo "    + $f"; done
echo "  bogus (passed against reverted impl): ${#BOGUS[@]}"
for f in "${BOGUS[@]}"; do echo "    - $f"; done

# Final restore — defense in depth in case run_one missed something.
git checkout HEAD -- src migrations 2>/dev/null || true

if [ "${#BOGUS[@]}" -gt 0 ]; then
  exit 1
fi
exit 0
