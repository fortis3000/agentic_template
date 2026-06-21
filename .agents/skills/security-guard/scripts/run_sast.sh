#!/usr/bin/env bash
# SAST Scanner Wrapper
# Runs Bandit static analysis on the codebase

status=0

echo "=== Running Bandit SAST Scan ==="
if uv run bandit -c pyproject.toml -r src/; then
  echo "SAST check: PASSED"
else
  echo "SAST check: FAILED"
  status=1
fi

exit $status
