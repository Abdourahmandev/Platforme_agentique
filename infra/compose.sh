#!/usr/bin/env bash
# Linux counterpart of compose.ps1: same runtime layout under $LOCALAPPDATA.
set -euo pipefail
export LOCALAPPDATA="${LOCALAPPDATA:-$HOME/.local/share}"
runtime="$LOCALAPPDATA/AsiaDocker"
if [[ ! -f "$runtime/litellm.env" ]]; then
    echo 'Runtime absent. Lancer infra/prepare-runtime-linux.py avant de demarrer.' >&2
    exit 1
fi
export ASIA_RUNTIME_DIR="$runtime"
exec docker compose -f "$(dirname "$(readlink -f "$0")")/compose.yaml" "$@"
