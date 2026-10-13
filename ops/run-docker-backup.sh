#!/usr/bin/env bash
# Linux counterpart of run-docker-backup.ps1, run daily by asia-backup.timer.
# Encrypted recovery point + isolated restore check, then keep the newest archives.
set -uo pipefail
export LOCALAPPDATA="${LOCALAPPDATA:-$HOME/.local/share}"
runtime="$LOCALAPPDATA/AsiaDocker"
archives="${ASIA_BACKUP_DIR:-$LOCALAPPDATA/AsiaBackups}"
keep="${ASIA_BACKUP_KEEP:-14}"
python="$LOCALAPPDATA/AsiaDockerOps/venv/bin/python"
result="$runtime/scheduled-backup-result.json"

# Never snapshot concurrently with a manual backup.
exec 9>"$LOCALAPPDATA/AsiaBackup/backup.lock"
flock -n 9 || { echo 'Another backup is running.'; exit 0; }

cd "$(dirname "$(readlink -f "$0")")"
if ! "$python" backup-docker.py --restore-check </dev/null; then
    printf '{"completed_at":"%s","passed":false}\n' "$(date -u +%FT%TZ)" > "$result"
    exit 1
fi
# Retention applies only to completed Docker archives, newest first.
ls -1t "$archives"/docker-*.aes 2>/dev/null | tail -n +"$((keep + 1))" | xargs -r rm -f --

# Off-site copy (optional): an rclone remote named by ASIA_BACKUP_REMOTE.
# Copy, never sync, so local loss cannot delete remote archives; age-based retention there.
# A failed upload is recorded but does not invalidate the local recovery point.
offsite=null
remote="${ASIA_BACKUP_REMOTE:-}"
if [[ -n "$remote" ]]; then
    if rclone copy "$archives" "$remote" --include 'docker-*.aes' --checksum \
       && rclone delete "$remote" --include 'docker-*.aes' --min-age "${ASIA_BACKUP_REMOTE_DAYS:-30}d"; then
        offsite=true
    else
        offsite=false
    fi
fi
printf '{"completed_at":"%s","passed":true,"offsite":%s}\n' "$(date -u +%FT%TZ)" "$offsite" > "$result"
