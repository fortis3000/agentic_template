#!/usr/bin/env bash
set -euo pipefail

echo "=== Running pre-commit hooks on all files ==="
if command -v uv >/dev/null 2>&1; then
    uv run pre-commit run --all-files
else
    pre-commit run --all-files
fi
