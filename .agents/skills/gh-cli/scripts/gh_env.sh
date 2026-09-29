#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
DOTENV="$ROOT_DIR/.env"

if [ ! -f "$DOTENV" ]; then
    echo "Error: .env file not found at $DOTENV" >&2
    exit 1
fi

TOKEN=$(grep -E "^(GH_TOKEN|GITHUB_TOKEN)=" "$DOTENV" | head -n 1 | cut -d= -f2- | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")

if [ -z "$TOKEN" ]; then
    echo "Error: GH_TOKEN or GITHUB_TOKEN not found in .env" >&2
    exit 1
fi

if [ "$1" = "activate" ]; then
    echo "Activating gh auth with token from .env..."
    printf "%s" "$TOKEN" | gh auth login --with-token
    echo "gh successfully authenticated with token from .env."
    exit 0
fi

export GH_TOKEN="$TOKEN"
export GITHUB_TOKEN="$TOKEN"

exec gh "$@"
