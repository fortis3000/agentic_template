#!/usr/bin/env bash
# Pre-commit guard hook for Claude Code
# Runs ruff check on changed Python files before git commit commands.
# Full validation is available via the /precommit skill.

input=$(cat)

# Only act on git commit commands
if ! echo "$input" | grep -q 'git commit'; then
  exit 0
fi

# Collect staged files only (don't block commits due to unstaged WIP)
changed_files="$(git diff --name-only --diff-filter=ACMR --staged | sort -u)"
python_files="$(printf '%s\n' "$changed_files" | grep -iE '\.py$' || true)"

if [ -z "$python_files" ]; then
  exit 0
fi

echo "Pre-commit hook: checking Python files with ruff..."
.venv/bin/ruff check -- $python_files
status=$?

if [ $status -ne 0 ]; then
  echo "BLOCKED: ruff check failed. Fix issues before committing."
  exit 1
fi

exit 0
