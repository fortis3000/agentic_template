#!/usr/bin/env bash
# Pre-commit validation script
# Runs linting, testing, and security checks on changed files.

echo "Collecting changed files..."
changed_files="$( (git diff --name-only --diff-filter=ACMR; git diff --name-only --diff-filter=ACMR --staged) | sort -u )"
python_files="$(printf '%s\n' "$changed_files" | grep -iE '\.py$' || true)"
md_files="$(printf '%s\n' "$changed_files" | grep -iE '\.md$' || true)"
test_files="$(printf '%s\n' "$changed_files" | grep -iE '(^|/)test_.*\.py$|_test\.py$' || true)"

if [ -z "$changed_files" ]; then
  echo "No changed files, skipping validation"
  exit 0
fi

status=0

# Python linting
if [ -n "$python_files" ]; then
  echo
  echo "=== Ruff format ==="
  .venv/bin/ruff format -- $python_files || status=1

  echo
  echo "=== Ruff check ==="
  .venv/bin/ruff check -- $python_files || status=1

  echo
  echo "=== Bandit security check ==="
  .venv/bin/bandit -c pyproject.toml -- $python_files || status=1
fi

# Markdown linting
if [ -n "$md_files" ]; then
  echo
  echo "=== Pymarkdown scan ==="
  .venv/bin/pymarkdown --disable-rules MD007,MD013,MD024,MD033 scan -- $md_files || status=1
fi

# Tests
if [ -n "$test_files" ]; then
  echo
  echo "=== Pytest ==="
  .venv/bin/python -m pytest -v -- $test_files || status=1
fi

echo
if [ $status -eq 0 ]; then
  echo "All checks passed"
else
  echo "Some checks failed"
fi

exit $status
