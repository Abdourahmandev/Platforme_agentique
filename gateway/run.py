"""Load existing credentials locally and start the loopback-only LiteLLM proxy."""
import json
import os
import secrets
import sys
from pathlib import Path

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, 'reconfigure'):
        stream.reconfigure(encoding='utf-8', errors='replace')
os.environ['PYTHONIOENCODING'] = 'utf-8'
os.environ['PYTHONUTF8'] = '1'
os.environ['PATH'] = str(Path(sys.executable).parent) + os.pathsep + os.environ.get('PATH', '')

folder = Path(__file__).resolve().parent
state = Path(os.environ['LOCALAPPDATA']) / 'AsiaLiteLLM'
state.mkdir(exist_ok=True)
master = state / 'gateway.key'
if not master.exists():
    master.write_text('sk-asia-' + secrets.token_urlsafe(40), encoding='utf-8')
auth_path = Path.home() / '.local/share/opencode/auth.json'
auth = json.loads(auth_path.read_text(encoding='utf-8-sig'))
key = auth.get('deepseek', {}).get('key')
if not key:
    raise SystemExit('DeepSeek credentials are unavailable in OpenCode.')
os.environ['DEEPSEEK_API_KEY'] = key
gemini_key = state / 'gemini.key'
if gemini_key.exists():
    os.environ['GEMINI_API_KEY'] = gemini_key.read_text(encoding='utf-8-sig').strip()
os.environ['LITELLM_MASTER_KEY'] = master.read_text(encoding='utf-8').strip()
database_file = state / 'database.json'
if database_file.exists():
    database = json.loads(database_file.read_text(encoding='utf-8'))
    os.environ['DATABASE_URL'] = database['url']
    os.environ['UI_USERNAME'] = database['ui_username']
    os.environ['UI_PASSWORD'] = database['ui_password']
    os.environ['LITELLM_SALT_KEY'] = database['salt_key']
os.environ['LITELLM_TELEMETRY'] = 'False'
os.environ['DO_NOT_TRACK'] = '1'
os.environ['LITELLM_LOG'] = 'ERROR'
sys.path.insert(0, str(folder))
os.chdir(folder)
from windows_prisma import install as install_windows_prisma
install_windows_prisma()
sys.argv = ['litellm', '--config', str(folder / 'config.yaml'), '--host', '127.0.0.1', '--port', '4000', '--telemetry', 'False']
from litellm.proxy.proxy_cli import run_server
run_server()
