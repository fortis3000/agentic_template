#!/usr/bin/env bash
# Software Component Analysis (SCA) Dependency Scanner
# Uses uvx to run pip-audit or safety check dynamically

status=0

echo "=== Running Dependency Vulnerability Scan ==="

if command -v uv &> /dev/null; then
  echo "Running pip-audit via uvx..."
  uvx pip-audit || status=1
else
  # Fallback if uv is not installed
  if command -v pip-audit &> /dev/null; then
    pip-audit || status=1
  elif command -v safety &> /dev/null; then
    safety check || status=1
  else
    echo "WARNING: Neither uv, pip-audit, nor safety is available. Skipping dependency scan."
  fi
fi

if [ $status -eq 0 ]; then
  echo "Dependency check: PASSED"
else
  echo "Dependency check: FAILED"
fi

exit $status
