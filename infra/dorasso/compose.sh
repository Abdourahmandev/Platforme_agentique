#!/usr/bin/env bash
# Dorasso stack (Hermes + private SearXNG), same layout as infra/compose.sh.
set -euo pipefail
export LOCALAPPDATA="${LOCALAPPDATA:-$HOME/.local/share}"
export DORASSO_DIR="$LOCALAPPDATA/Dorasso"
export DORASSO_DATA_DIR="$DORASSO_DIR/data"
if [[ ! -f "$DORASSO_DATA_DIR/.env" ]]; then
    echo 'Runtime Dorasso absent. Lancer infra/dorasso/prepare-dorasso.py.' >&2
    exit 1
fi
exec docker compose -f "$(dirname "$(readlink -f "$0")")/compose.yaml" "$@"
