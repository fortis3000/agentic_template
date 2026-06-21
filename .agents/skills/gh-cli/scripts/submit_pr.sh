#!/usr/bin/env bash
# submit_pr.sh: Run tests, commit, push, and create a Pull Request with a semantic commit message.
# Usage: bash submit_pr.sh <type> [scope] <description>
# Examples:
#   bash submit_pr.sh feat auth "add google login"
#   bash submit_pr.sh fix "resolve db deadlock"

set -e

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

# 1. Run local precommit checks if the script exists
if [ -f ".agents/skills/python-pr-prep/scripts/precommit.sh" ]; then
  echo "Running pre-commit checks..."
  bash .agents/skills/python-pr-prep/scripts/precommit.sh
else
  echo "No local precommit check script found, staging files directly..."
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
