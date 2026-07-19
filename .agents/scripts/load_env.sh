#!/usr/bin/env bash
# Project-scoped secret loader — no machine-wide tooling required.
#
# Usage (from the repo root or a worktree):
#   source .agents/scripts/load_env.sh
#
# Exports GITHUB_TOKEN from the repo's .env, falling back to the parent dir's .env
# (handy inside a git worktree under .worktrees/) so `gh` authenticates out-of-the-box.
# Safe to source repeatedly; does nothing if no non-empty token is found.
#
# This is the same logic the optional .envrc (direnv) uses, so the two stay in sync.

__load_github_token() {
  local env_file="$1"
  [ -f "$env_file" ] || return 1
  local token
  token="$(grep -E '^GITHUB_TOKEN=' "$env_file" | head -n1 | cut -d= -f2- | xargs)"
  [ -n "$token" ] || return 1
  export GITHUB_TOKEN="$token"
  echo "load_env: exported GITHUB_TOKEN from $env_file" >&2
  return 0
}

if __load_github_token "$PWD/.env"; then
  :
elif __load_github_token "$PWD/../.env"; then
  :
else
  echo "load_env: no non-empty GITHUB_TOKEN found in ./.env or ../.env" >&2
fi

unset -f __load_github_token
