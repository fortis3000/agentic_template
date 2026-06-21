#!/usr/bin/env bash
# start_issue.sh: Start implementing a GitHub issue
# Usage: bash start_issue.sh <issue_number> [optional_branch_name]

set -e

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

# 2. Create the linked branch and check it out
if [ -n "$branch_name" ]; then
  echo "Creating linked branch '$branch_name' for issue #$issue_number..."
  gh issue develop "$issue_number" --checkout --name "$branch_name"
else
  echo "Creating linked branch for issue #$issue_number..."
  gh issue develop "$issue_number" --checkout
fi

echo "Ready to start implementing issue #$issue_number!"
