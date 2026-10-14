"""Verify MCP calls in a real synthetic Asia turn, without Telegram delivery."""
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
import requests

RUNTIME = Path(os.environ['LOCALAPPDATA']) / 'AsiaDocker'
DOCKER = (r'C:\Program Files\Docker\Docker\resources\bin\docker.exe' if os.name == 'nt' else 'docker')
EXEC = [DOCKER, 'exec', '-i', 'asia-platform-staging-openclaw-1']


def main():
    private = json.loads((RUNTIME / 'runtime-private.json').read_text())
    headers = {'Authorization': 'Bearer ' + private['gateway_token']}
    fixture = 'migration-agent-tools-' + uuid.uuid4().hex
    session = 'agent:asia:' + fixture
    prompt = ("Test technique sur des donnees artificielles. Commence obligatoirement par tool_search puis tool_describe pour lire les schemas des outils MCP necessaires. Ne devine aucun parametre. Execute les etapes sequentiellement. "
              "1) Appelle tavily__tavily_search pour 'site:docs.openclaw.ai Telegram' avec 2 resultats. "
              "2) Appelle playwright__browser_navigate sur https://example.com puis playwright__browser_snapshot. "
              f"3) Appelle asia-memory__create_entities pour l'entite {fixture}, de type migration-test, "
              "avec l'observation synthetic-agent-marker ; puis asia-memory__open_nodes pour la relire. "
              "4) Ferme le navigateur via playwright__browser_close. "
              "Ne cree aucun fichier avec write/edit. Termine par les resultats factuels, sans inventer de succes.")
    checks = {}
    def check(name, passed):
        checks[name] = bool(passed)
        print(json.dumps({name: bool(passed)}), flush=True)
    try:
        run = subprocess.run(EXEC + ['node', 'dist/index.js', 'agent', '--agent', 'asia',
                             '--session-key', session, '--message', prompt, '--timeout', '300', '--json'],
                             capture_output=True, timeout=330)
        (RUNTIME / 'asia-tools-agent-private.json').write_bytes(run.stdout)
        (RUNTIME / 'asia-tools-agent-private.log').write_bytes(run.stderr)
        check('agent_turn_completed', run.returncode == 0)
        response = requests.post('http://127.0.0.1:18789/tools/invoke', headers=headers,
                                 json={'tool': 'sessions_history', 'agentId': 'asia', 'sessionKey': session,
                                       'args': {'sessionKey': session, 'includeTools': True, 'limit': 100}}, timeout=30)
        body = response.json()
        (RUNTIME / 'asia-tools-history-private.json').write_text(json.dumps(body))
        result = body.get('result', {})
        history = result.get('details', {})
        if not isinstance(history, dict) or 'messages' not in history:
            for item in result.get('content', []):
                if item.get('type') == 'text':
                    try:
                        history = json.loads(item['text'])
                        if 'messages' in history: break
                    except ValueError:
                        pass
        calls, successes = {}, set()
        for message in history.get('messages', []):
            role = message.get('role')
            if role == 'assistant':
                for part in message.get('content', []):
                    if not isinstance(part, dict) or part.get('type') not in ('toolCall', 'tool_use'):
                        continue
                    name, args = part.get('name'), part.get('arguments', part.get('input', {}))
                    if name == 'tool_call' and isinstance(args, dict):
                        name = args.get('name', args.get('tool', args.get('id', '').split(':')[-1]))
                    calls[part.get('id')] = name
            if role in ('toolResult', 'tool') and not message.get('isError', False):
                nested_error = False
                for part in message.get('content', []):
                    if not isinstance(part, dict) or part.get('type') != 'text':
                        continue
                    try:
                        value = json.loads(part['text'])
                        nested_error |= isinstance(value, dict) and bool(value.get('result', {}).get('isError'))
                    except (ValueError, AttributeError):
                        pass
                name = calls.get(message.get('toolCallId', message.get('tool_call_id')))
                if name and not nested_error: successes.add(name)
        for name in ('tavily__tavily_search', 'playwright__browser_navigate', 'playwright__browser_snapshot',
                     'asia-memory__create_entities', 'asia-memory__open_nodes'):
            check(name, name in successes)
        graph = subprocess.run(EXEC + ['node', '-e',
              'const fs=require("fs"),p="/home/node/.openclaw/workspaces/asia/memory.jsonl";process.stdout.write(fs.existsSync(p)?fs.readFileSync(p):"missing")'],
              capture_output=True, timeout=20)
        check('agent_memory_on_disk', fixture.encode() in graph.stdout and b'synthetic-agent-marker' in graph.stdout)
        current = subprocess.run(EXEC + ['node', '-e',
                'process.stdout.write(require("fs").readFileSync("/home/node/.openclaw/openclaw.json"))'],
                capture_output=True, timeout=20)
        config = json.loads(current.stdout)
        for agent in ('developpement', 'recherche'):
            denied = config['agents']['entries'][agent]['tools']['deny']
            check(agent + '_connector_policy', all(n in denied for n in ('tavily__*', 'asia-memory__*', 'playwright__*')))
    except Exception as exc:
        check('suite_completed', False)
        print(json.dumps({'error_type': type(exc).__name__}))
    finally:
        # Delete only our uniquely named synthetic entity, using the same MCP.
        cleanup = f'''import {{Client}} from '/app/node_modules/@modelcontextprotocol/sdk/dist/esm/client/index.js';
import {{StdioClientTransport}} from '/app/node_modules/@modelcontextprotocol/sdk/dist/esm/client/stdio.js';
const c=new Client({{name:'cleanup',version:'1'}},{{capabilities:{{}}}});
try {{await c.connect(new StdioClientTransport({{command:'npx',args:['--yes','--offline','@modelcontextprotocol/server-memory@1.0.0'],env:{{PATH:process.env.PATH,HOME:process.env.HOME,MEMORY_FILE_PATH:'/home/node/.openclaw/workspaces/asia/memory.jsonl'}},stderr:'pipe'}}));
const r=await c.callTool({{name:'delete_entities',arguments:{{entityNames:[{json.dumps(fixture)}]}}}});if(r.isError)process.exitCode=1;}} finally {{await c.close();}}
'''
        cleaned = subprocess.run(EXEC + ['node', '--input-type=module'], input=cleanup.encode(), capture_output=True, timeout=40)
        check('memory_fixture_removed', cleaned.returncode == 0)
        report = {'checks': checks, 'passed': bool(checks) and all(checks.values())}
        (RUNTIME / 'asia-tools-test-result.json').write_text(json.dumps(report, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
