"""Prepare Dorasso's private Hermes data directory; never print secrets.

Inputs (private, 0600): $LOCALAPPDATA/Dorasso/telegram.token and litellm-key.json.
Writes data/.env, data/config.yaml and data/SOUL.md once; refuses to overwrite.
Usage: prepare-dorasso.py <owner Telegram user id>
"""
import json
import os
import shutil
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get('LOCALAPPDATA') or Path.home() / '.local/share') / 'Dorasso'
DATA = ROOT / 'data'
MODEL = 'gemini-3.8-flash'  # Gemini only: personal data stays off DeepSeek

CONFIG = f"""# Dorasso: Hermes routed through LiteLLM (Gemini models only, own team budget).
model:
  provider: litellm
  default: {MODEL}
  api_mode: chat_completions
providers:
  litellm:
    api: http://litellm:4000/v1
    api_key: "${{DORASSO_LITELLM_KEY}}"
    discover_models: false
    models:
      {MODEL}: {{}}
      gemini-3.1-pro-preview: {{}}
      gemini-3.1-flash-lite: {{}}
stt:
  enabled: true
  echo_transcripts: false
  provider: openai
  language: fr
  openai:
    # Speaches on this server: voice notes are transcribed locally.
    model: Systran/faster-whisper-base
    base_url: http://speaches:8000/v1
    api_key: "${{DORASSO_SPEECH_KEY}}"
tts:
  provider: openai
  openai:
    # tts-proxy converts Gemini WAV to Opus; billed to Dorasso's LiteLLM key.
    model: gemini-3.8-flash-lite-tts
    voice: Kore
    base_url: http://tts-proxy:8080/v1
    api_key: "${{DORASSO_LITELLM_KEY}}"
plugins:
  enabled:
    - dorasso-voice-only
"""


def write_private(path, text):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(text)


def main():
    if len(sys.argv) != 2 or not sys.argv[1].isdecimal():
        raise SystemExit('Usage: prepare-dorasso.py <owner Telegram user id>')
    if (DATA / '.env').exists() or (DATA / 'config.yaml').exists():
        raise SystemExit('Dorasso data already initialized; refusing to replace it.')
    token = (ROOT / 'telegram.token').read_text().strip()
    key = json.loads((ROOT / 'litellm-key.json').read_text())['key']
    speech = json.loads((ROOT.parent / 'AsiaDocker/runtime-private.json').read_text())['speech_key']
    for value in (token, key, speech):
        if any(c in value for c in '\r\n "\'\\$'):
            raise ValueError('Unsupported character in secret')
    DATA.mkdir(mode=0o700, parents=True, exist_ok=True)
    write_private(DATA / '.env', ''.join(f'{k}={v}\n' for k, v in {
        'TELEGRAM_BOT_TOKEN': token,
        'TELEGRAM_ALLOWED_USERS': sys.argv[1],
        'DORASSO_LITELLM_KEY': key,
        'DORASSO_SPEECH_KEY': speech,
    }.items()))
    write_private(DATA / 'config.yaml', CONFIG)
    write_private(DATA / 'SOUL.md', (HERE / 'SOUL.md').read_text(encoding='utf-8'))
    # Voice notes answered with a voice bubble only (see the plugin docstring).
    shutil.copytree(HERE / 'plugins', DATA / 'plugins', dirs_exist_ok=True)
    print(f'Dorasso data prepared in {DATA} (owner {sys.argv[1]}, model {MODEL}).')


if __name__ == '__main__':
    main()
