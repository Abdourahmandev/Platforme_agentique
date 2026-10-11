"""Create three agent identities and bounded staging keys in Docker LiteLLM."""
import json
import os
from pathlib import Path
import shutil
import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path(os.environ['LOCALAPPDATA']) / 'AsiaDocker'
AGENTS = {'asia': 'Asia', 'developpement': 'Developpement', 'recherche': 'Recherche'}
TEAM = 'asia-platform-staging'
ROUTES = ['/chat/completions', '/v1/chat/completions', '/models', '/v1/models',
          '/embeddings', '/v1/embeddings', '/images/generations', '/v1/images/generations',
          '/audio/speech', '/v1/audio/speech', '/audio/transcriptions', '/v1/audio/transcriptions']


def main():
    private_path = RUNTIME / 'runtime-private.json'
    private = json.loads(private_path.read_text())
    if private.get('phase') != 'staging':
        raise SystemExit('This provisioner is restricted to staging.')
    config_path = RUNTIME / 'openclaw/openclaw.json'
    if config_path.exists():
        raise SystemExit('OpenClaw already configured; refusing to overwrite live agent configuration.')
    client = requests.Session()
    client.headers['Authorization'] = 'Bearer ' + private['master_key']

    def post(path, payload):
        response = client.post('http://127.0.0.1:14000' + path, json=payload, timeout=30)
        if not response.ok:
            raise RuntimeError(f'LiteLLM {path} returned HTTP {response.status_code}')
        return response.json()

    catalogue = yaml.safe_load((ROOT / 'gateway/config.yaml').read_text(encoding='utf-8'))['model_list']
    models = [row['model_name'] for row in catalogue]
    if not private.get('team_created'):
        post('/team/new', {'team_id': TEAM, 'team_alias': 'Migration staging', 'max_budget': 1,
                          'budget_duration': '30d', 'models': models, 'rpm_limit': 30})
        private['team_created'] = True
        private_path.write_text(json.dumps(private))
    keys = private.setdefault('agent_keys', {})
    for agent_id in AGENTS:
        if agent_id not in keys:
            keys[agent_id] = post('/key/generate', {
                'key_alias': 'staging-' + agent_id, 'team_id': TEAM, 'models': models,
                'allowed_routes': ROUTES, 'key_type': 'llm_api', 'max_budget': 0.3,
                'budget_duration': '30d', 'rpm_limit': 15, 'max_parallel_requests': 2,
                'metadata': {'agent_id': agent_id, 'environment': 'staging'},
            })['key']
            private_path.write_text(json.dumps(private))
        agent_dir = RUNTIME / 'openclaw/agents' / agent_id / 'agent'
        agent_dir.mkdir(parents=True, exist_ok=True)
        (agent_dir / 'auth-profiles.json').write_text(json.dumps({
            'version': 1, 'profiles': {'litellm:default': {
                'type': 'api_key', 'provider': 'litellm', 'key': keys[agent_id],
            }}, 'order': {'litellm': ['litellm:default']},
        }), encoding='utf-8')
        workspace = RUNTIME / 'openclaw/workspaces' / agent_id
        workspace.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / 'infra/agents' / agent_id / 'AGENTS.md', workspace / 'AGENTS.md')
        (workspace / 'IDENTITY.md').write_text(f'# Identite\n\nNom : {AGENTS[agent_id]}\nIdentifiant : {agent_id}\n', encoding='utf-8')
    config = json.loads((ROOT / 'infra/openclaw.example.json').read_text())
    config['models']['providers']['litellm']['models'] = [{
        'id': row['model_name'], 'name': row['model_name'],
        'input': ['text', 'image'] if row['model_info'].get('supports_vision') else ['text'],
        'contextWindow': min(row['model_info'].get('max_input_tokens', 128000), 128000),
        'maxTokens': 4096, 'reasoning': False,
        'compat': {'maxTokensField': 'max_tokens', 'supportsDeveloperRole': False,
                   'supportsStore': False, 'supportsReasoningEffort': False},
    } for row in catalogue if row['model_info']['mode'] == 'chat']
    config_path.write_text(json.dumps(config, indent=2), encoding='utf-8')
    print(json.dumps({'agents': list(AGENTS), 'shared_staging_budget_usd': 1,
                      'per_agent_staging_budget_usd': 0.3, 'telegram_enabled': False}))


if __name__ == '__main__':
    main()
