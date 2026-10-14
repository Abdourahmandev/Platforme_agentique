"""Wake agents left idle on an actionable Paperclip ticket (run every 2 minutes).

Observed in Paperclip 2026.1005.0: when an executor finishes during its own run,
the issue is reassigned to the review-stage agent but that agent is not woken,
so the ticket waits forever. This sweeper wakes an agent that holds a `todo`,
`in_progress` or `in_review` ticket, has no queued or running heartbeat run, and
whose ticket has not changed for 3 minutes. The idempotency key includes the
ticket's last update, so each state change triggers at most one wake: a failing
agent is never retried in a loop. Owner-assigned tickets are never touched.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import requests

PRIVATE = Path(os.environ.get('LOCALAPPDATA') or Path.home() / '.local/share') / 'AsiaPaperclip'
API = 'http://127.0.0.1:3100/api'
IDLE_SECONDS = 180
ACTIONABLE = {'todo', 'in_progress', 'in_review'}
ACTIVE_RUNS = {'queued', 'running', 'scheduled_retry'}


def main():
    token = json.loads((PRIVATE / 'board-token.json').read_text())['token']
    company = json.loads((PRIVATE / 'company.json').read_text())['id']
    s = requests.Session()
    s.headers['Authorization'] = 'Bearer ' + token
    runs = s.get(f'{API}/companies/{company}/heartbeat-runs', params={'limit': 100}, timeout=30).json()
    runs = runs.get('items', runs) if isinstance(runs, dict) else runs
    busy = {r.get('agentId') for r in runs if r.get('status') in ACTIVE_RUNS}
    # After a timed-out run Paperclip leaves the agent in `error`, and wakes are then
    # accepted without starting a run. Clearing it counts against the daily cap below.
    agent_status = {a['id']: a.get('status') for a in s.get(f'{API}/companies/{company}/agents', timeout=30).json()}
    now = datetime.now(timezone.utc)
    # Hard cap independent of Paperclip's idempotency: 3 wakes per ticket per day.
    state_path = PRIVATE / 'idle-wake-state.json'
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    today = now.date().isoformat()
    state = {k: v for k, v in state.items() if v.get('day') == today}
    for issue in s.get(f'{API}/companies/{company}/issues', timeout=30).json():
        agent = issue.get('assigneeAgentId')
        if issue.get('status') not in ACTIONABLE or not agent or issue.get('assigneeUserId') or agent in busy:
            continue
        updated = datetime.fromisoformat(issue['updatedAt'].replace('Z', '+00:00'))
        if (now - updated).total_seconds() < IDLE_SECONDS:
            continue
        entry = state.setdefault(issue['id'], {'day': today, 'count': 0, 'last': None})
        if entry['count'] >= 3 or entry['last'] == issue['updatedAt']:
            continue
        entry['count'] += 1
        entry['last'] = issue['updatedAt']
        if agent_status.get(agent) == 'error':
            cleared = s.post(f'{API}/agents/{agent}/clear-error', json={}, timeout=30)
            print(f"{issue['identifier']} -> agent en erreur remis en service: {cleared.status_code}", flush=True)
            agent_status[agent] = 'idle'
        elif agent_status.get(agent) == 'paused':
            continue  # a human paused it on purpose
        key = f"idle-wake-{issue['id']}-{issue['updatedAt']}"
        r = s.post(f'{API}/agents/{agent}/wakeup', timeout=30, json={
            'source': 'assignment', 'triggerDetail': 'system', 'idempotencyKey': key,
            'reason': f"Reveil automatique : {issue['identifier']} attend cet agent sans passage actif",
            'payload': {'issueId': issue['id']}})
        print(f"{issue['identifier']} -> reveil {r.status_code} ({entry['count']}/3 aujourd'hui)", flush=True)
        busy.add(agent)
    tmp = state_path.with_suffix('.tmp')
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as f:
        json.dump(state, f)
    tmp.replace(state_path)


if __name__ == '__main__':
    main()
