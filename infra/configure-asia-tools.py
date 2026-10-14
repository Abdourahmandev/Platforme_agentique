"""Restore Asia's web/browser/memory capabilities without activating its bot.

Google is intentionally excluded. Secrets and before-images stay outside Git.
Run --prepare-env, recreate only OpenClaw, then --apply. No Telegram edits.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = Path(os.environ['LOCALAPPDATA']) / 'AsiaDocker'
DOCKER = (r'C:\Program Files\Docker\Docker\resources\bin\docker.exe' if os.name == 'nt' else 'docker')
CONTAINER = 'asia-platform-staging-openclaw-1'
TOOLS = ['playwright__*', 'tavily__*', 'asia-memory__*']
BRIDGE_TOOLS = ['asia_opencode_task', 'asia_opencode_approve']
MEMORY_PACKAGE = '@modelcontextprotocol/server-memory@1.0.0'


def credential(value):
    match = re.fullmatch(r'\{env:([A-Z_][A-Z_0-9]*)\}', value)
    if match:
        name = match[1]
        value = os.environ.get(name, '')
        if not value and os.name == 'nt':
            import winreg
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment') as registry:
                    value = winreg.QueryValueEx(registry, name)[0]
            except FileNotFoundError:
                pass
    if not value or any(c in value for c in '\r\n\"\'${}'):
        raise ValueError('Tavily credential unavailable or unsupported reference')
    return value


def run(args, data=None, timeout=180):
    result = subprocess.run([DOCKER, 'exec', '-i', CONTAINER, *args],
                            input=data, capture_output=True, timeout=timeout)
    if result.returncode:
        (RUNTIME / 'asia-tools-error.log').write_bytes(result.stdout + result.stderr)
        raise RuntimeError('OpenClaw operation failed; private diagnostic saved')
    return result.stdout


def patch_for(current):
    """Preserve existing policies; scope the new capabilities to Asia only."""
    plugin_entries = {'asia-opencode': {'enabled': True}}
    # Speech uses OpenAI's protocol adapter against local Speaches. It was
    # previously auto-enabled and must survive an explicit plugin allowlist.
    if any(model.get('provider') == 'openai' for model in current.get('tools', {}).get('media', {}).get('models', [])):
        plugin_entries['openai'] = {'enabled': True}
    global_allow = [name for name in current['tools']['allow'] if name != 'browser']
    entries = current['agents']['entries']
    if 'asia' not in entries:
        raise ValueError('Asia is missing')
    policies = {}
    for agent, entry in entries.items():
        policy = deepcopy(entry.get('tools', {}))
        allow = [name for name in policy.get('allow', global_allow) if name != 'browser']
        policy['allow'] = list(dict.fromkeys(allow + (TOOLS + BRIDGE_TOOLS if agent == 'asia' else [])))
        if agent != 'asia':
            # Preserve a separately enabled Windows bridge for Souleiman.
            bridge_enabled = agent == 'developpement' and all(t in allow for t in BRIDGE_TOOLS)
            policy['deny'] = list(dict.fromkeys(policy.get('deny', []) + TOOLS + ([] if bridge_enabled else BRIDGE_TOOLS)))
        policies[agent] = {'tools': policy}
    return {
        'tools': {'allow': list(dict.fromkeys(global_allow + TOOLS + BRIDGE_TOOLS))},
        # The JSONL memory server is not a cross-process transactional database.
        # Serialize agent turns on this small host to avoid concurrent writers.
        'agents': {'defaults': {'maxConcurrent': 1}, 'entries': policies},
        'browser': {'enabled': False},
        'plugins': {'entries': plugin_entries,
                    'allow': list(dict.fromkeys(current.get('plugins', {}).get('allow', []) +
                               list(current.get('plugins', {}).get('entries', {})) + list(plugin_entries)))},
        'approvals': {'plugin': {'enabled': True, 'mode': 'session', 'agentFilter': ['asia']}},
        'mcp': {'sessionIdleTtlMs': 300000, 'servers': {
            'playwright': {
                'url': 'http://playwright:8931/mcp', 'transport': 'streamable-http',
                'connectionTimeoutMs': 20000, 'requestTimeoutMs': 60000,
                'toolFilter': {'exclude': ['browser_run_code', 'browser_install']},
            },
            'tavily': {
                'url': 'https://mcp.tavily.com/mcp/', 'transport': 'streamable-http',
                'headers': {'Authorization': 'Bearer ${ASIA_TAVILY_API_KEY}'},
                'connectionTimeoutMs': 20000, 'requestTimeoutMs': 60000,
                'toolFilter': {'include': ['tavily_search', 'tavily_extract', 'tavily_map', 'tavily_crawl']},
            },
            'asia-memory': {
                'command': 'npx', 'args': ['--yes', '--offline', MEMORY_PACKAGE],
                'env': {'MEMORY_FILE_PATH': '/home/node/.openclaw/workspaces/asia/memory.jsonl'},
                'connectionTimeoutMs': 20000, 'requestTimeoutMs': 30000,
                'supportsParallelToolCalls': False,
            },
        }},
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepare-env', action='store_true')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    legacy = json.loads((Path.home() / '.config/opencode/opencode.json').read_text(encoding='utf-8-sig'))
    if args.prepare_env:
        key = credential(legacy['mcp']['search']['environment']['TAVILY_API_KEY'])
        env_file = RUNTIME / 'openclaw.env'
        before = env_file.read_text()
        lines = [line for line in before.splitlines() if not line.startswith('ASIA_TAVILY_API_KEY=')]
        (RUNTIME / 'openclaw-before-asia-tools.env').write_text(before)
        env_file.write_text('\n'.join(lines) + '\nASIA_TAVILY_API_KEY=' + key + '\n')
        print('Tavily credential prepared privately. Recreate OpenClaw before --apply.')
        return
    current = json.loads(run(['node', '-e', 'process.stdout.write(require("fs").readFileSync("/home/node/.openclaw/openclaw.json"))']))
    if args.apply:
        # Native extension and secrets are separate from all agent workspaces.
        for source in (ROOT / 'infra/opencode-bridge').iterdir():
            if source.suffix not in ('.mjs', '.json'):
                continue
            dest = '/home/node/.openclaw/extensions/asia-opencode/' + source.name
            run(['node', '-e', 'const fs=require("fs"),p=process.argv[1];fs.mkdirSync(require("path").dirname(p),{recursive:true,mode:0o700});fs.writeFileSync(p,fs.readFileSync(0),{mode:0o600})', dest], source.read_bytes())
        auth = json.loads((Path(os.environ['LOCALAPPDATA']) / 'OpenCodeWeb/server-secret.json').read_text())
        auth['directory'] = str(Path.home() / 'Documents/OpenCode')
        run(['node', '-e', 'require("fs").writeFileSync("/home/node/.openclaw/credentials/asia-opencode.json",require("fs").readFileSync(0),{mode:0o600})'], json.dumps(auth).encode())
    patch = patch_for(current)
    raw = json.dumps(patch).encode()
    run(['node', 'dist/index.js', 'config', 'patch', '--stdin', '--dry-run', '--json'], raw)
    if not args.apply:
        print('Asia tool patch validated; Telegram unchanged.')
        return
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    (RUNTIME / ('before-asia-tools-' + stamp + '.json')).write_text(json.dumps(current))
    memory_path = Path(legacy['mcp']['memory']['environment']['MEMORY_FILE_PATH'])
    if memory_path.exists():
        raise RuntimeError('Existing memory requires an explicit import before activation')
    initialized = subprocess.run([DOCKER, 'compose', '-f', str(ROOT / 'infra/compose.yaml'),
                                  '--profile', 'bootstrap', 'run', '--rm', '--no-deps', 'openclaw-tools-init'],
                                 env=dict(os.environ, ASIA_RUNTIME_DIR=RUNTIME.as_posix()),
                                 capture_output=True, timeout=90)
    if initialized.returncode:
        raise RuntimeError('MCP cache initialization failed')
    # Populate a reinstallable cache once; runtime starts use --offline.
    run(['npm', 'exec', '--yes', '--package=' + MEMORY_PACKAGE, '--', 'node', '--version'], timeout=240)
    run(['node', 'dist/index.js', 'config', 'patch', '--stdin'], raw)
    run(['node', 'dist/index.js', 'config', 'validate'])
    run(['node', '-e', 'require("fs").writeFileSync("/home/node/.openclaw/workspaces/asia/AGENTS.md",require("fs").readFileSync(0),{mode:0o600})'],
        (ROOT / 'infra/agents/asia/AGENTS.md').read_bytes())
    print('Asia web, browser and dedicated MCP memory configured. Live tests still required. Telegram unchanged.')


if __name__ == '__main__':
    main()
