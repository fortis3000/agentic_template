#!/usr/bin/env bash
# start_issue.sh: Start implementing a GitHub issue
# Usage: bash start_issue.sh <issue_number> [optional_branch_name]

set -e

# Load GitHub token from .env if available
if [ -f .env ]; then
  token=$(grep -E "^(GH_TOKEN|GITHUB_TOKEN)=" .env | head -n 1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")
  if [ -n "$token" ]; then
    export GH_TOKEN="$token"
  fi
fi

# If no issue number is provided, list open issues
if [ -z "$1" ]; then
  echo "No issue number provided. Listing recent open issues:"
  gh issue list --limit 10
  echo
  echo "Usage: bash .agents/skills/gh-cli/scripts/start_issue.sh <issue_number> [optional_branch_name]"
  exit 1
fi

issue_number="$1"
branch_name="$2"

# 1. Assign the issue to the current user
echo "Assigning issue #$issue_number to @me..."
gh issue edit "$issue_number" --add-assignee @me

# 2. Create the linked branch and set up the Git worktree
if [ -z "$branch_name" ]; then
  # Default branch name to issue-<number>
  branch_name="issue-${issue_number}"
fi

# Ensure .worktrees directory exists
mkdir -p .worktrees

if [ -d ".worktrees/$branch_name" ]; then
  echo "Worktree directory '.worktrees/$branch_name' already exists."
  echo "You can navigate to it using: cd .worktrees/$branch_name"
  exit 0
fi

# Create linked branch on GitHub
echo "Creating linked branch '$branch_name' for issue #$issue_number..."
gh issue develop "$issue_number" --name "$branch_name" || echo "Branch might already exist on remote. Proceeding..."

# Fetch remote refs to see the newly created branch
echo "Fetching origin..."
git fetch origin || true

# Add the git worktree
if git show-ref --verify --quiet "refs/remotes/origin/$branch_name"; then
  echo "Checking out tracking branch origin/$branch_name into worktree..."
  git worktree add ".worktrees/$branch_name" "origin/$branch_name"
elif git show-ref --verify --quiet "refs/heads/$branch_name"; then
  echo "Checking out existing local branch $branch_name into worktree..."
  git worktree add ".worktrees/$branch_name" "$branch_name"
else
  echo "Creating new local branch $branch_name and checking out into worktree..."
  # Find base branch
  base_branch="main"
  if ! git show-ref --verify --quiet "refs/heads/main"; then
    if git show-ref --verify --quiet "refs/heads/master"; then
      base_branch="master"
    else
      base_branch="$(git symbolic-ref --short HEAD)"
    fi
  fi
  git worktree add -b "$branch_name" ".worktrees/$branch_name" "origin/$base_branch" 2>/dev/null || \
  git worktree add -b "$branch_name" ".worktrees/$branch_name" "$base_branch"
fi

echo "Worktree created successfully at .worktrees/$branch_name!"
echo "To start working, run:"
echo "  cd .worktrees/$branch_name"
echo "  uv sync --extra all"
echo "Ready to start implementing issue #$issue_number!"

