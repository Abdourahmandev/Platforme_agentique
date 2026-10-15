"""Allow Asia's asia_notion tool in OpenClaw (Asia only), with a private rollback snapshot."""
import json
import sys
import control as c

sys.path.insert(0, str(c.ROOT / 'infra/training'))
import common as g

TOOL = 'asia_notion'


def main():
    config = g.remote_json(g.BASE + '/openclaw.json')
    c.save('openclaw-before-notion.json', config)
    if TOOL not in config['tools']['allow']:
        config['tools']['allow'].append(TOOL)
    allow = config['agents']['entries']['asia']['tools']['allow']
    if TOOL not in allow:
        allow.append(TOOL)
    g.remote_write(g.BASE + '/openclaw.json', json.dumps(config, ensure_ascii=False, indent=2))
    try:
        g.docker('exec', g.GATEWAY, 'node', 'dist/index.js', 'config', 'validate', '--json')
    except Exception:
        g.remote_write(g.BASE + '/openclaw.json', json.dumps(c.read('openclaw-before-notion.json'), ensure_ascii=False, indent=2))
        raise
    print('asia_notion autorise pour Asia ; configuration OpenClaw validee.')


if __name__ == '__main__':
    main()
