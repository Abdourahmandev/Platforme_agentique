#!/usr/bin/env bash
# Store the Notion integration secret for the notion-bridge (read from stdin, never echoed).
# Usage: bash infra/notion-bridge/set-notion-token.sh   then paste the secret, Enter, Ctrl+D.
set -euo pipefail
dir="${LOCALAPPDATA:-$HOME/.local/share}/Notion"
token="$(tr -d '\r\n ')"
[[ "$token" == ntn_* || "$token" == secret_* ]] || { echo 'Cle refusee : une cle d integration Notion (ntn_... ou secret_...) est attendue.' >&2; exit 1; }
name="$(curl -fsS https://api.notion.com/v1/users/me -H "Authorization: Bearer $token" -H 'Notion-Version: 2022-06-28' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin).get("name") or "?")')" || { echo 'Notion a refuse la cle.' >&2; exit 1; }
install -d -m 700 "$dir"
umask 077
printf 'NOTION_TOKEN=%s\n' "$token" > "$dir/notion.env.tmp"
mv "$dir/notion.env.tmp" "$dir/notion.env"
echo "Cle Notion enregistree pour l integration : $name"
