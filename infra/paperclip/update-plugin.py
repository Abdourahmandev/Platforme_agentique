"""Redeploy the asia-paperclip plugin and refresh its credentials (projects, agents).

install-plugin.py runs once (it keeps the rollback snapshot); this script only
copies the plugin files again and rewrites credentials.json from the private
deployment state: the shared default project, named factory projects with their
QA reviewer, and every Paperclip agent (agents without a Paperclip key file, such
as Maryam, are assignable but cannot call the tool). Never prints secrets.
Usage: update-plugin.py [--project "slug=Project name:reviewer:reviewFor"] ...
"""
import argparse
import json
import sys
import requests
import control as c

sys.path.insert(0, str(c.ROOT / 'infra/training'))
import common as g


def paperclip_projects(company_id):
    token = c.read('board-token.json')['token']
    response = requests.get(f'http://127.0.0.1:3100/api/companies/{company_id}/projects',
                            headers={'Authorization': 'Bearer ' + token}, timeout=30)
    response.raise_for_status()
    return {p['name']: p['id'] for p in response.json()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--project', action='append', default=[],
                        help='"slug=Project name:reviewer:reviewFor" (reviewer and reviewFor optional)')
    args = parser.parse_args()
    state = c.read('deployment.json')
    company = c.read('company.json')
    catalogue = json.loads((c.ROOT / 'infra/agents/catalogue.json').read_text(encoding='utf-8'))
    names = {'maryam': 'Maryam', **{k: v['name'] for k, v in catalogue.items()}}
    agents = {}
    for name, value in state['agents'].items():
        entry = {'id': value['id'], 'name': names.get(name, name)}
        try:
            entry['token'] = c.read('key-' + name + '.json')['token']
        except FileNotFoundError:
            pass  # assignable only
        agents[name] = entry

    projects = dict(state.get('plugin_projects', {}))
    if args.project:
        ids = paperclip_projects(company['id'])
        for spec in args.project:
            slug, _, rest = spec.partition('=')
            name, reviewer, review_for = (rest.split(':') + ['', ''])[:3]
            if not slug or name not in ids:
                raise SystemExit(f'Unknown Paperclip project: {name!r}')
            projects[slug] = {'id': ids[name], 'name': name,
                              **({'reviewer': reviewer} if reviewer else {}),
                              **({'reviewFor': review_for} if review_for else {})}
    for slug, project in projects.items():
        for role in ('reviewer', 'reviewFor'):
            if project.get(role) and project[role] not in agents:
                raise SystemExit(f'{role} {project[role]!r} of project {slug} is not a provisioned agent')
    state['plugin_projects'] = projects
    c.save('deployment.json', state)

    for source in (c.ROOT / 'infra/paperclip/plugin').iterdir():
        if source.is_file():
            g.remote_write(g.BASE + '/extensions/asia-paperclip/' + source.name, source.read_text(encoding='utf-8'))
    default = c.read('project.json')
    credentials = {'enabled': True, 'apiUrl': 'http://paperclip:3100',
                   'publicUrl': state['public_url'].rstrip('/') + '/' + company['issuePrefix'],
                   'companyId': company['id'], 'projectId': default['id'], 'projectName': default['name'],
                   'defaultProject': 'plateforme', 'projects': projects,
                   'ownerId': c.read('owner.json')['userId'], 'agents': agents}
    bridge = c.PRIVATE.parent / 'Notion/bridge.env'
    if bridge.exists():  # Asia's Notion tool (infra/notion-bridge)
        key = bridge.read_text().strip().partition('=')[2]
        credentials['notion'] = {'url': 'http://notion-bridge:8080', 'key': key}
    g.remote_write(g.BASE + '/paperclip-control/credentials.json', json.dumps(credentials))
    print(json.dumps({'projects': ['plateforme', *sorted(projects)],
                      'agents': {k: ('outil' if 'token' in v else 'assignable') for k, v in agents.items()}}))


if __name__ == '__main__':
    main()
