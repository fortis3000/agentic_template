#!/usr/bin/env bash
# Secrets Scanner Wrapper
# Runs the custom python secrets scanner and checks for trufflehog/gitleaks

status=0

echo "=== Running Secrets Scan ==="

# Execute custom python scanner
uv run python .agents/skills/security-guard/scripts/scan_secrets.py || status=1

# Check for GitLeaks in path
if command -v gitleaks &> /dev/null; then
  echo "Found gitleaks, running gitleaks detect..."
  gitleaks detect --verbose || status=1
fi

# Check for Trufflehog in path
if command -v trufflehog &> /dev/null; then
  echo "Found trufflehog, running trufflehog git..."
  trufflehog git file://$(pwd) --only-verified || status=1
fi

if [ $status -eq 0 ]; then
  echo "Secrets check: PASSED"
else
  echo "Secrets check: FAILED"
fi

exit $status
