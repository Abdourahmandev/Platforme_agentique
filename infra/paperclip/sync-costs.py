"""Attribute real LiteLLM spend to Paperclip tickets (run every 10 minutes).

Paperclip records each agent run with its ticket but prices nothing (our models go
through LiteLLM). LiteLLM records each request with the agent's key alias, time,
model and cost, but knows no ticket. This job joins them: a request belongs to the
run of the same agent that started before it, until that run finishes plus a grace
period (a timed-out run's process may keep spending until the reaper stops it) or
the agent's next run starts. Each finished run is then posted once to Paperclip as
cost events (one per model, biller "litellm"), so tickets, projects and agents show
real dollars in Paperclip and to Asia. Requests outside any run (Telegram chats,
Dorasso) are personal or conversational and are never attributed. Never prints keys.
"""
import argparse
import json
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
import requests

LOCAL = Path(os.environ.get('LOCALAPPDATA') or Path.home() / '.local/share')
PRIVATE = LOCAL / 'AsiaPaperclip'
API = 'http://127.0.0.1:3100/api'
LITELLM = 'http://127.0.0.1:14000'
GRACE = timedelta(minutes=60)
# Paperclip agent slug -> LiteLLM key aliases used by that agent's runs.
ALIASES = {'developpement': {'souleiman-atelier'}, 'maryam': {'maryam-atelier'},
           'recherche': {'saredo-atelier', 'Saredo'}, 'asia': {'staging-asia'}}


def when(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')) if value else None


def attribute(runs, logs, now):
    """Return {run_id: {model: {'spend', 'input', 'output'}}} for runs ready to post."""
    by_agent = defaultdict(list)
    for run in runs:
        if run.get('startedAt'):
            by_agent[run['agentSlug']].append(run)
    windows = []
    for slug, items in by_agent.items():
        items.sort(key=lambda r: r['startedAt'])
        for i, run in enumerate(items):
            start = when(run['startedAt'])
            end = (when(run['finishedAt']) or now) + GRACE
            if i + 1 < len(items):
                end = min(end, when(items[i + 1]['startedAt']))
            windows.append((slug, start, end, run))
    totals = defaultdict(lambda: defaultdict(lambda: {'spend': 0.0, 'input': 0, 'output': 0}))
    for log in logs:
        at = when(log['startTime'])
        for slug, start, end, run in windows:
            if log['alias'] in ALIASES.get(slug, ()) and start <= at < end:
                bucket = totals[run['id']][log['model']]
                bucket['spend'] += float(log['spend'] or 0)
                bucket['input'] += int(log.get('prompt_tokens') or 0)
                bucket['output'] += int(log.get('completion_tokens') or 0)
                break
    return totals


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help='print totals per ticket, post nothing')
    args = parser.parse_args()
    board = requests.Session()
    board.headers['Authorization'] = 'Bearer ' + json.loads((PRIVATE / 'board-token.json').read_text())['token']
    company = json.loads((PRIVATE / 'company.json').read_text())['id']
    slugs = {v['id']: k for k, v in json.loads((PRIVATE / 'deployment.json').read_text())['agents'].items()}
    runs = board.get(f'{API}/companies/{company}/heartbeat-runs', params={'limit': 1000}, timeout=60).json()
    runs = runs.get('items', runs) if isinstance(runs, dict) else runs
    for run in runs:
        run['agentSlug'] = slugs.get(run['agentId'])
    first = min((r['startedAt'] for r in runs if r.get('startedAt')), default=None)
    if not first:
        return
    master = json.loads((LOCAL / 'AsiaDocker/runtime-private.json').read_text())['master_key']
    now = datetime.now(timezone.utc)
    raw = requests.get(f'{LITELLM}/spend/logs', headers={'Authorization': 'Bearer ' + master}, timeout=120, params={
        'start_date': first[:10], 'end_date': (now + timedelta(days=1)).date().isoformat(), 'summarize': 'false'}).json()
    raw = raw if isinstance(raw, list) else raw.get('data', [])
    logs = [{'alias': (x.get('metadata') or {}).get('user_api_key_alias') if isinstance(x.get('metadata'), dict) else None,
             'model': x.get('model') or x.get('model_group') or 'inconnu', 'startTime': x['startTime'], 'spend': x.get('spend'),
             'prompt_tokens': x.get('prompt_tokens'), 'completion_tokens': x.get('completion_tokens')}
            for x in raw if x.get('startTime') and (x.get('status') in (None, 'success'))]
    totals = attribute(runs, logs, now)

    state_path = PRIVATE / 'cost-sync-state.json'
    state = json.loads(state_path.read_text()) if state_path.exists() else {'posted': []}
    posted = set(state['posted'])
    issues, summary = {}, defaultdict(float)
    for run in runs:
        issue_id = (run.get('contextSnapshot') or {}).get('issueId')
        finished = when(run.get('finishedAt'))
        if run['id'] in posted or not issue_id or not finished or finished + GRACE > now or run['id'] not in totals:
            continue
        if issue_id not in issues:
            issues[issue_id] = board.get(f'{API}/issues/{issue_id}', timeout=30).json()
        issue = issues[issue_id]
        for model, t in totals[run['id']].items():
            summary[issue.get('identifier', issue_id)] += t['spend']
            cents = round(t['spend'] * 100)
            if args.dry_run or cents == 0:
                continue
            r = board.post(f'{API}/companies/{company}/cost-events', timeout=30, json={
                'agentId': run['agentId'], 'issueId': issue_id, 'projectId': issue.get('projectId'),
                'heartbeatRunId': run['id'], 'provider': model.split('/')[0], 'biller': 'litellm',
                'billingType': 'metered_api', 'model': model, 'costCents': cents,
                'occurredAt': finished.isoformat().replace('+00:00', 'Z')})
            r.raise_for_status()
        if not args.dry_run:
            posted.add(run['id'])
    if not args.dry_run:
        tmp = state_path.with_suffix('.tmp')
        tmp.write_text(json.dumps({'posted': sorted(posted)}))
        tmp.replace(state_path)
    for key, value in sorted(summary.items()):
        print(f'{key}: {value:.2f} $')


if __name__ == '__main__':
    main()
