#!/usr/bin/env bash
# submit_pr.sh: Run tests, commit, push, and create a Pull Request with a semantic commit message.
# Usage: bash submit_pr.sh <type> [scope] <description>
# Examples:
#   bash submit_pr.sh feat auth "add google login"
#   bash submit_pr.sh fix "resolve db deadlock"

set -e

# Load GitHub token from .env if available
if [ -f .env ]; then
  token=$(grep -E "^(GH_TOKEN|GITHUB_TOKEN)=" .env | head -n 1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")
  if [ -n "$token" ]; then
    export GH_TOKEN="$token"
  fi
fi

# Verify arguments
if [ "$#" -lt 2 ]; then
  echo "Error: Missing arguments."
  echo "Usage: bash .agents/skills/gh-cli/scripts/submit_pr.sh <type> [scope] <description>"
  echo "Allowed types: feat, fix, docs, style, refactor, perf, test, build, ci, chore"
  exit 1
fi

commit_type="$1"
# Ensure type is valid
case "$commit_type" in
  feat|fix|docs|style|refactor|perf|test|build|ci|chore) ;;
  *)
    echo "Warning: '$commit_type' is not a standard commit type (feat, fix, docs, style, refactor, perf, test, build, ci, chore)."
    ;;
esac

if [ "$#" -eq 2 ]; then
  scope=""
  description="$2"
else
  scope="$2"
  description="$3"
fi

# 1. Run Docker-sandboxed validation checks (Ruff, Bandit, Pytest)
echo "Checking if Docker is available for sandboxed validation..."
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  echo "Docker daemon is running. Building validation container..."
  # Build using the Dockerfile in the current directory (which is copied/accessible in the worktree)
  docker build -f docker/Dockerfile -t agentic-template:latest .

  echo "Running sandboxed validations inside Docker container..."
  docker run --rm -v "$(pwd)":/app -v /app/.venv agentic-template:latest bash -c "
    set -e
    echo '=== Syncing all dependencies (including dev) inside container ==='
    uv sync --locked --extra all
    echo '=== Ruff format check ==='
    uv run ruff format --check src/ tests/
    echo '=== Ruff lint check ==='
    uv run ruff check src/ tests/
    echo '=== ty type check ==='
    uv run ty check src/ tests/
    echo '=== Bandit security check ==='
    uv run bandit -c pyproject.toml -r src/
    echo '=== Pytest ==='
    uv run python -m pytest -v
  "
else
  echo "WARNING: Docker is not running or not installed. Running local validation fallback..."
  if [ -f "precommit.sh" ]; then
    bash precommit.sh
  elif [ -f ".agents/skills/python-pr-prep/scripts/precommit.sh" ]; then
    bash .agents/skills/python-pr-prep/scripts/precommit.sh
  elif command -v uv >/dev/null 2>&1; then
    uv run pre-commit run
  else
    pre-commit run
  fi
fi


# 2. Stage all changes
echo "Staging all changes..."
git add -A

# Check if there are changes to commit
if git diff --cached --quiet; then
  echo "No changes to commit. Aborting."
  exit 0
fi

# 3. Create semantic commit message
if [ -n "$scope" ]; then
  commit_msg="${commit_type}(${scope}): ${description}"
else
  commit_msg="${commit_type}: ${description}"
fi

echo "Committing with message: '$commit_msg'..."
git commit -m "$commit_msg"

# 4. Push to remote
echo "Pushing branch to remote..."
git push -u origin HEAD

# 5. Create Pull Request
echo "Creating Pull Request on GitHub..."
gh pr create --fill --draft

echo "Pull Request successfully created!"
