#!/usr/bin/env bash
# Tester Subagent Verification Script
# Runs formatting, linting, typing, and pytest verification on changed files

status=0

echo "Collecting changed files..."
changed_files="$( (git diff --name-only --diff-filter=ACMR; git diff --name-only --diff-filter=ACMR --staged) | sort -u )"
python_files="$(printf '%s\n' "$changed_files" | grep -iE '\.py$' || true)"

if [ -n "$python_files" ]; then
  echo "=== Ruff format check ==="
  uv run ruff format --check $python_files || status=1

  echo
  echo "=== Ruff check ==="
  uv run ruff check $python_files || status=1

  echo
  echo "=== ty type check ==="
  uv run ty check $python_files || status=1
else
  echo "No changed python files to lint/typecheck."
fi

echo
echo "=== Running Pytest Suite ==="
PYTHONPATH=. uv run pytest -v || status=1

echo
if [ $status -eq 0 ]; then
  echo "SUCCESS: All verification checks passed."
else
  echo "FAILURE: Verification checks failed."
fi

exit $status
