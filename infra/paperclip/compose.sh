#!/usr/bin/env bash
# Linux counterpart of compose.ps1 for the Paperclip stack.
set -euo pipefail
export LOCALAPPDATA="${LOCALAPPDATA:-$HOME/.local/share}"
private="$LOCALAPPDATA/AsiaPaperclip"
if [[ ! -f "$private/paperclip.env" ]]; then
    echo 'Runtime Paperclip absent. Lancer infra/paperclip/prepare-paperclip-linux.py.' >&2
    exit 1
fi
export ASIA_PAPERCLIP_DIR="$private"
exec docker compose -f "$(dirname "$(readlink -f "$0")")/compose.yaml" "$@"
