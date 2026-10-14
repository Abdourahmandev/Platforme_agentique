"""Route OpenClaw text-to-speech through LiteLLM (Gemini TTS) instead of Microsoft Edge.

The Edge read-aloud endpoint rejects OpenClaw's client (HTTP 403). The `openai`
TTS adapter is used only for its protocol: requests go to tts-proxy (WAV to Opus
for Telegram voice notes, see infra/tts-proxy), then to the internal LiteLLM
gateway with a dedicated key, bounded and charged to the shared team budget.
Default validates; --apply creates the key (once) and saves the configuration.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import requests

RUNTIME = Path(os.environ.get('LOCALAPPDATA') or Path.home() / '.local/share') / 'AsiaDocker'
DOCKER = r'C:\Program Files\Docker\Docker\resources\bin\docker.exe' if os.name == 'nt' else 'docker'
CLI = [DOCKER, 'exec', '-i', 'asia-platform-staging-openclaw-1', 'node', 'dist/index.js']
TEAM = 'asia-platform-staging'
MODEL = 'gemini-3.8-flash-tts'
VOICE = 'Kore'


def command(args, data=None):
    result = subprocess.run(CLI + args, input=data, capture_output=True, timeout=90)
    if result.returncode:
        (RUNTIME / 'tts-configuration-error.log').write_bytes(result.stdout + result.stderr)
        raise RuntimeError('TTS configuration failed. Diagnostic saved in the private runtime.')
    return result.stdout


def tts_config(key):
    current = json.loads(command(['config', 'get', 'tts', '--json']))
    providers = dict(current.get('providers', {}))
    providers['openai'] = {'baseUrl': 'http://tts-proxy:8080/v1', 'apiKey': key, 'model': MODEL,
                           'speakerVoice': VOICE}
    # Only [[tts:text]] is honoured: agents may make a reply voice-only, never switch
    # provider, voice or model. An empty visible text makes OpenClaw send audio alone.
    overrides = {'enabled': True, 'allowText': True, 'allowProvider': False, 'allowVoice': False,
                 'allowModelId': False, 'allowVoiceSettings': False, 'allowNormalization': False,
                 'allowSeed': False}
    return dict(current, provider='openai', providers=providers, modelOverrides=overrides)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    path = RUNTIME / 'runtime-private.json'
    state = json.loads(path.read_text())
    key = state.get('tts_key', 'sk-placeholder-for-validation')
    if args.apply and 'tts_key' not in state:
        r = requests.post('http://127.0.0.1:14000/key/generate', timeout=30,
                          headers={'Authorization': 'Bearer ' + state['master_key']},
                          json={'key_alias': 'tts', 'team_id': TEAM, 'models': [MODEL],
                                'allowed_routes': ['/audio/speech', '/v1/audio/speech'], 'key_type': 'llm_api',
                                'max_budget': 3, 'budget_duration': '30d', 'rpm_limit': 15,
                                'max_parallel_requests': 2, 'metadata': {'purpose': 'openclaw-tts'}})
        if not r.ok:
            raise RuntimeError(f'LiteLLM /key/generate returned HTTP {r.status_code}')
        key = state['tts_key'] = r.json()['key']
        path.write_text(json.dumps(state))
    config = tts_config(key)
    command(['config', 'set', 'tts', json.dumps(config), '--strict-json', '--dry-run'])
    if not args.apply:
        print('TTS gateway configuration validated; no change applied.')
        return
    command(['config', 'set', 'tts', json.dumps(config), '--strict-json'])
    command(['config', 'validate'])
    print(f'TTS now uses {MODEL} ({VOICE}) through LiteLLM with a dedicated $3/30d key.')


if __name__ == '__main__':
    main()
