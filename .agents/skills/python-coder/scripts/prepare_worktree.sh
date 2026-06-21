#!/usr/bin/env bash
# Git Worktree Preparation Script
# Automates creation of an isolated workspace branch for coding tasks

if [ -z "$1" ]; then
  echo "Usage: $0 <branch-name>"
  exit 1
fi

BRANCH_NAME="$1"
WORKTREE_DIR=".worktrees/$BRANCH_NAME"

if [ -d "$WORKTREE_DIR" ]; then
  echo "Directory $WORKTREE_DIR already exists."
  exit 0
fi

echo "Creating isolated Git worktree under $WORKTREE_DIR..."
git worktree add -b "$BRANCH_NAME" "$WORKTREE_DIR" origin/master
