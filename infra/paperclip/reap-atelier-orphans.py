"""Stop atelier processes whose Paperclip run has ended (run every 2 minutes).

Observed in Paperclip 2026.1005.0: when an opencode_local run in the SSH
environment times out or is cancelled, Paperclip marks it ended but leaves the
remote `opencode run` (and its bridge) running in the atelier. Orphans keep
calling the model, compete with the next run and may push stale work. Each
process is mapped to its run through the run directory in its working directory
or command line; it is stopped only when Paperclip reports that run as ended.
Any doubt (API error, unknown run) leaves the process alone.
"""
import json
import os
import re
import subprocess
from pathlib import Path
import requests

PRIVATE = Path(os.environ.get('LOCALAPPDATA') or Path.home() / '.local/share') / 'AsiaPaperclip'
API = 'http://127.0.0.1:3100/api'
CONTAINER = 'atelier-atelier-1'
ACTIVE_RUNS = {'queued', 'running', 'scheduled_retry'}
RUN_DIR = re.compile(r'/\.paperclip-runtime/runs/([0-9a-f-]{36})/')
# One line per candidate process: "<pid>\t<cwd>\t<command line>".
LIST = r'''for p in $(pgrep -f "opencode run|paperclip-bridge-server"); do
  printf '%s\t%s\t%s\n' "$p" "$(readlink /proc/$p/cwd)" "$(tr '\0' ' ' < /proc/$p/cmdline)"; done'''


def atelier(*args):
    return subprocess.run(['docker', 'exec', '-u', 'node', CONTAINER, *args],
                          capture_output=True, text=True, timeout=30)


def main():
    listing = atelier('sh', '-c', LIST)
    if listing.returncode != 0:
        return
    token = json.loads((PRIVATE / 'board-token.json').read_text())['token']
    session = requests.Session()
    session.headers['Authorization'] = 'Bearer ' + token
    status = {}
    for line in listing.stdout.splitlines():
        pid, cwd, cmd = (line.split('\t') + ['', ''])[:3]
        match = RUN_DIR.search(cwd + '/') or RUN_DIR.search(cmd)
        if not match:
            continue
        run_id = match.group(1)
        if run_id not in status:
            r = session.get(f'{API}/heartbeat-runs/{run_id}', timeout=30)
            status[run_id] = r.json().get('status') if r.ok else None
        if status[run_id] and status[run_id] not in ACTIVE_RUNS:
            atelier('kill', pid)
            print(f'processus {pid} arrete (execution {run_id[:8]} : {status[run_id]})')


if __name__ == '__main__':
    main()
