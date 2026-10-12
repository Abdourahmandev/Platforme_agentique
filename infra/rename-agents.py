"""Staged display-name migration. Private snapshot; stable IDs and keys retained."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
def load_helper(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

c = load_helper('agent_names_paperclip_control', 'infra/paperclip/control.py')
g = load_helper('agent_names_gateway_common', 'infra/training/common.py')

CATALOGUE = json.loads((ROOT / 'infra/agents/catalogue.json').read_text(encoding='utf-8'))
SPECIALISTS = ('developpement', 'recherche')
SNAPSHOT = 'agent-names-before.json'
JOURNAL = 'agent-names-progress.json'
IDENTITY_NOTE = '\n\n## Noms des agents\n\nSouleiman est le nouveau nom de Developpement (identifiant stable `developpement`). Saredo est le nouveau nom de Recherche (identifiant stable `recherche`). Asia conserve son nom et son identifiant `asia`. Les anciens noms restent des alias comprehensibles. Utilise les nouveaux noms dans tes reponses et les identifiants stables dans les appels d outils. Les roles, droits, historiques et memoires sont conserves.\n'


def renamed_text(text, identity_note=False):
    for old, new in [('Développement', 'Souleiman'), ('Developpement', 'Souleiman'), ('Recherche', 'Saredo')]:
        text = text.replace(old, new)
    if identity_note:
        if '## Noms des agents' in text:
            raise ValueError('Identity note already exists; reconcile instead of appending twice')
        text = text.rstrip() + IDENTITY_NOTE
    return text


def renamed_config(config):
    result = deepcopy(config)
    for aid in SPECIALISTS:
        result['agents']['entries'][aid]['name'] = CATALOGUE[aid]['name']
        result['channels']['telegram']['accounts'][aid]['name'] = CATALOGUE[aid]['name']
    return result


def remote_text(filename):
    return g.node('process.stdout.write(require("fs").readFileSync(JSON.parse(require("fs").readFileSync(0))))', filename).decode('utf-8')


def telegram(aid, method, data=None):
    cfg = g.remote_json(g.BASE + '/openclaw.json')
    token = remote_text(cfg['channels']['telegram']['accounts'][aid]['tokenFile']).strip()
    try:
        response = requests.post('https://api.telegram.org/bot' + token + '/' + method,
                                 json=data or {}, timeout=25)
        if response.ok and response.json().get('ok'):
            return response.json()['result']
    except (requests.RequestException, ValueError):
        pass
    raise RuntimeError('Telegram ' + method + ' failed; no credential-bearing URL logged')


def key_info(aid):
    state = g.private_state()
    try:
        r = requests.get('http://127.0.0.1:14000/key/info', params={'key': state['agent_keys'][aid]},
                         headers={'Authorization': 'Bearer ' + state['master_key']}, timeout=25)
        if r.ok:
            return r.json()['info']
    except (requests.RequestException, ValueError):
        pass
    raise RuntimeError('Private LiteLLM key read failed')


def key_alias(aid, name):
    state = g.private_state()
    r = requests.post('http://127.0.0.1:14000/key/update',
                      json={'key': state['agent_keys'][aid], 'key_alias': name},
                      headers={'Authorization': 'Bearer ' + state['master_key']}, timeout=25)
    if not r.ok:
        raise RuntimeError('LiteLLM alias update failed: HTTP ' + str(r.status_code))


def journal(stage, state, **details):
    record = c.read(JOURNAL) if (c.PRIVATE / JOURNAL).exists() else {}
    record[stage] = {'state': state, 'at': datetime.now(timezone.utc).isoformat(), **details}
    c.save(JOURNAL, record)


def snapshot():
    if (c.PRIVATE / SNAPSHOT).exists():
        raise RuntimeError('Snapshot already exists; it must never be overwritten')
    cl = c.Client().login()
    agents = cl.request('GET', '/companies/' + c.read('company.json')['id'] + '/agents')
    assert all(a['status'] == 'idle' for a in agents), 'Wait for active Paperclip work'
    files = {}
    for aid in CATALOGUE:
        for name in ('AGENTS.md', 'IDENTITY.md', 'PROCEDURES.md'):
            filename = g.BASE + '/workspaces/' + aid + '/' + name
            files[filename] = remote_text(filename)
    for rel in ('openclaw.json', 'paperclip-control/credentials.json',
                'extensions/asia-paperclip/index.mjs', 'extensions/asia-paperclip/tickets.mjs'):
        files[g.BASE + '/' + rel] = remote_text(g.BASE + '/' + rel)
    state = {'at': datetime.now(timezone.utc).isoformat(), 'files': files, 'paperclip': agents,
             'keys': {aid: key_info(aid) for aid in CATALOGUE}, 'telegram': {},
             'keyDigests': {aid: hashlib.sha256(key.encode()).hexdigest()
                            for aid, key in g.private_state()['agent_keys'].items()}}
    for aid in SPECIALISTS:
        state['telegram'][aid] = {'bot': telegram(aid, 'getMe'), 'languages': {}}
        for lang in ('', 'fr', 'en'):
            state['telegram'][aid]['languages'][lang] = {
                method: telegram(aid, method, {'language_code': lang})
                for method in ('getMyName', 'getMyDescription', 'getMyShortDescription')}
    state['tickets'] = cl.request('GET', '/companies/' + c.read('company.json')['id'] + '/issues?limit=100')
    state['workspaceInventory'] = json.loads(g.node('''const fs=require('fs'),path=require('path'),crypto=require('crypto');
const roots=JSON.parse(fs.readFileSync(0));const out={};function walk(p){for(const e of fs.readdirSync(p,{withFileTypes:true})){const f=path.join(p,e.name);if(e.isDirectory())walk(f);else if(e.isFile())out[f]=crypto.createHash('sha256').update(fs.readFileSync(f)).digest('hex');}}for(const p of roots)walk(p);process.stdout.write(JSON.stringify(out));''',
        [g.BASE + '/workspaces/' + a for a in CATALOGUE]))
    c.save(SNAPSHOT, state)
    assert c.read(SNAPSHOT) == state
    journal('snapshot', 'complete', files=len(files), tickets=len(state['tickets']))
    print(json.dumps({'snapshotVerified': True, 'files': len(files), 'tickets': len(state['tickets'])}))


def apply_openclaw(saved):
    original = json.loads(saved['files'][g.BASE + '/openclaw.json'])
    assert g.remote_json(g.BASE + '/openclaw.json') == original, 'Configuration drift; review before applying'
    target = dict(saved['files'])
    target[g.BASE + '/openclaw.json'] = json.dumps(renamed_config(original), ensure_ascii=False, indent=2)
    for aid in CATALOGUE:
        for name in ('AGENTS.md', 'IDENTITY.md', 'PROCEDURES.md'):
            filename = g.BASE + '/workspaces/' + aid + '/' + name
            target[filename] = renamed_text(saved['files'][filename], identity_note=name == 'AGENTS.md')
    for name in ('index.mjs', 'tickets.mjs'):
        target[g.BASE + '/extensions/asia-paperclip/' + name] = (ROOT / 'infra/paperclip/plugin' / name).read_text(encoding='utf-8')
    credfile = g.BASE + '/paperclip-control/credentials.json'
    creds = json.loads(saved['files'][credfile])
    for aid in CATALOGUE:
        creds['agents'][aid]['name'] = CATALOGUE[aid]['name']
    target[credfile] = json.dumps(creds, ensure_ascii=False, indent=2)
    c.save('agent-names-target-private.json', {'files': target})
    # Check every preimage before any write; backups retain the original content.
    for filename, original_text in saved['files'].items():
        assert remote_text(filename) == original_text, 'Runtime file drift: ' + filename
    for filename, content in target.items():
        g.remote_write(filename, content)
    for filename, content in target.items():
        assert remote_text(filename) == content, 'Runtime verification failed'
    g.docker('exec', g.GATEWAY, 'node', 'dist/index.js', 'config', 'validate', '--json')
    print(json.dumps({'openclawFilesVerified': len(target), 'restartRequired': True}))


def apply_paperclip(saved):
    cl = c.Client().login()
    for old in saved['paperclip']:
        aid = old.get('adapterConfig', {}).get('agentId')
        if aid not in SPECIALISTS:
            continue
        current = cl.request('GET', '/agents/' + old['id'])
        assert current['name'] in (old['name'], CATALOGUE[aid]['name']), 'Unexpected Paperclip name'
        if current['name'] != CATALOGUE[aid]['name']:
            cl.request('PATCH', '/agents/' + old['id'], {'name': CATALOGUE[aid]['name']})
        result = cl.request('GET', '/agents/' + old['id'])
        assert result['name'] == CATALOGUE[aid]['name']
        for key in ('id', 'adapterConfig', 'runtimeConfig', 'role', 'reportsTo', 'permissions', 'budgetMonthlyCents'):
            assert result.get(key) == old.get(key), 'Paperclip field unexpectedly changed: ' + key
        print(json.dumps({'paperclipName': result['name'], 'stableIdPreserved': True}))


def apply_telegram(saved):
    for aid in SPECIALISTS:
        name = CATALOGUE[aid]['name']
        short = name + ' - ' + CATALOGUE[aid]['role'] + '. Agent personnel coordonne par Asia.'
        for lang in ('', 'fr', 'en'):
            for method, key, value in [('setMyName', 'name', name), ('setMyDescription', 'description', short),
                                       ('setMyShortDescription', 'short_description', short)]:
                telegram(aid, method, {key: value, 'language_code': lang})
            assert telegram(aid, 'getMyName', {'language_code': lang})['name'] == name
            assert telegram(aid, 'getMyDescription', {'language_code': lang})['description'] == short
            assert telegram(aid, 'getMyShortDescription', {'language_code': lang})['short_description'] == short
        bot = telegram(aid, 'getMe')
        assert all(bot[k] == saved['telegram'][aid]['bot'][k] for k in ('id', 'username'))
        print(json.dumps({'telegramName': name, 'username': bot['username'], 'botIdPreserved': True}))


def apply_litellm(saved):
    for aid in SPECIALISTS:
        old = saved['keys'][aid]
        current = key_info(aid)
        assert current['key_alias'] in (old['key_alias'], CATALOGUE[aid]['name']), 'Unexpected LiteLLM alias'
        key_alias(aid, CATALOGUE[aid]['name'])
        result = key_info(aid)
        assert result['key_alias'] == CATALOGUE[aid]['name']
        for field in ('max_budget', 'budget_duration', 'budget_reset_at', 'team_id', 'models', 'metadata', 'rpm_limit', 'tpm_limit', 'max_parallel_requests'):
            assert result.get(field) == old.get(field), 'LiteLLM policy changed: ' + field
        assert result['spend'] >= old['spend'], 'Spend counter went backwards'
        print(json.dumps({'litellmAlias': result['key_alias'], 'budgetPreserved': True, 'spendPreserved': True}))


def rollback(saved):
    # Refuse to overwrite files edited after this migration.
    target = c.read('agent-names-target-private.json')['files'] if (c.PRIVATE / 'agent-names-target-private.json').exists() else {}
    for filename, old in saved['files'].items():
        assert remote_text(filename) in (old, target.get(filename)), 'Rollback conflict: ' + filename
    cl = c.Client().login()
    agents = cl.request('GET', '/companies/' + c.read('company.json')['id'] + '/agents')
    assert all(a['status'] == 'idle' for a in agents), 'Wait for active Paperclip work before rollback'
    # Preflight external names too, before making any rollback writes.
    for old in saved['paperclip']:
        aid = old.get('adapterConfig', {}).get('agentId')
        if aid in SPECIALISTS:
            current = cl.request('GET', '/agents/' + old['id'])
            assert current['name'] in (old['name'], CATALOGUE[aid]['name']), 'Paperclip rollback conflict'
    for aid in SPECIALISTS:
        assert key_info(aid)['key_alias'] in (saved['keys'][aid]['key_alias'], CATALOGUE[aid]['name']), 'LiteLLM rollback conflict'
        bot = telegram(aid, 'getMe')
        assert all(bot[k] == saved['telegram'][aid]['bot'][k] for k in ('id', 'username')), 'Telegram identity changed'
        short = CATALOGUE[aid]['name'] + ' - ' + CATALOGUE[aid]['role'] + '. Agent personnel coordonne par Asia.'
        for lang, previous in saved['telegram'][aid]['languages'].items():
            for method, field, target_value in [('Name', 'name', CATALOGUE[aid]['name']),
                                                 ('Description', 'description', short),
                                                 ('ShortDescription', 'short_description', short)]:
                value = telegram(aid, 'getMy' + method, {'language_code': lang})[field]
                assert value in (previous['getMy' + method][field], target_value), 'Telegram rollback conflict'
    for old in saved['paperclip']:
        aid = old.get('adapterConfig', {}).get('agentId')
        if aid in SPECIALISTS:
            current = cl.request('GET', '/agents/' + old['id'])
            assert current['name'] in (old['name'], CATALOGUE[aid]['name']), 'Paperclip rollback conflict'
            cl.request('PATCH', '/agents/' + old['id'], {'name': old['name']})
    for aid in SPECIALISTS:
        for lang, previous in saved['telegram'][aid]['languages'].items():
            for method, field in [('Name', 'name'), ('Description', 'description'), ('ShortDescription', 'short_description')]:
                telegram(aid, 'setMy' + method, {field: previous['getMy' + method][field], 'language_code': lang})
        key_alias(aid, saved['keys'][aid]['key_alias'])
    for filename, old in saved['files'].items():
        g.remote_write(filename, old)
    print('Original display names restored. Restart OpenClaw; no tickets, sessions or counters restored.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', choices=['snapshot', 'openclaw', 'paperclip', 'telegram', 'litellm', 'rollback'], required=True)
    stage = parser.parse_args().stage
    if stage == 'snapshot':
        snapshot()
        return
    saved = c.read(SNAPSHOT)
    progress = c.read(JOURNAL)
    if stage != 'rollback' and stage in progress:
        raise RuntimeError('Stage already attempted; inspect the private journal before reconciliation')
    journal(stage, 'pending')
    {'openclaw': apply_openclaw, 'paperclip': apply_paperclip, 'telegram': apply_telegram,
     'litellm': apply_litellm, 'rollback': rollback}[stage](saved)
    journal(stage, 'complete')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Requests exceptions may contain a private query string. Keep diagnostics private.
        (c.PRIVATE / 'agent-names-error-private.txt').write_text(type(error).__name__ + ': ' + str(error), encoding='utf-8')
        print('Stage failed; inspect the private diagnostic and reconcile before retrying.')
        raise SystemExit(1) from None
