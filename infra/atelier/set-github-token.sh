#!/usr/bin/env bash
# Store the atelier's own GitHub credential (fine-grained PAT read from stdin).
# Paperclip only brokers GitHub access for SSH environments when a Paperclip
# GitHub (OAuth) connection exists; without one, runs use the host's own
# credentials. The token is readable by the atelier agents: keep it limited to
# the factory repositories, without administration rights.
set -euo pipefail
dir="${LOCALAPPDATA:-$HOME/.local/share}/Atelier/gh"
token="$(tr -d '\r\n ' )"
[[ "$token" == github_pat_* ]] || { echo 'Jeton refuse : un jeton fine-grained (github_pat_...) est attendu.' >&2; exit 1; }
user="$(curl -fsS -H "Authorization: Bearer $token" https://api.github.com/user | python3 -c 'import sys,json;print(json.load(sys.stdin)["login"])')"
install -d -m 700 "$dir"
umask 077
printf 'github.com:\n    oauth_token: %s\n    user: %s\n    git_protocol: https\n' "$token" "$user" > "$dir/hosts.yml.tmp"
mv "$dir/hosts.yml.tmp" "$dir/hosts.yml"
echo "Identifiants GitHub de l'atelier enregistres pour $user ($(wc -c < "$dir/hosts.yml") octets)."
