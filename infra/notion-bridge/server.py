"""Notion bridge: Asia's only way into Notion, limited to the "Projets Decidata" database.

Reads the Notion integration token from NOTION_TOKEN_FILE (written by the owner's
secret page or set-notion-token.sh); agents get a narrow HTTP API on the internal
`agents` network, authenticated by BRIDGE_KEY. It can only:
- create the database once, under the page titled "Decidata" shared with the integration;
- list, create and update project pages of that database;
- append sections (heading + paragraphs / bullet points) to those pages.
Every page id is checked to belong to the database. Nothing else in the workspace is
read or written, and neither the token nor page contents are logged.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import re
import threading
import urllib.error
import urllib.request

NOTION = 'https://api.notion.com/v1'
VERSION = '2022-06-28'
PARENT_TITLE = os.environ.get('NOTION_PARENT_TITLE', 'Decidata')
DB_TITLE = os.environ.get('NOTION_DB_TITLE', 'Projets Decidata')
STATUSES = ['Besoin', 'Conception', 'Estimation', 'En cours', 'Termine', 'En pause', 'Abandonne']
# API field -> (Notion property, type)
FIELDS = {
    'name': ('Nom', 'title'),
    'status': ('Statut', 'select'),
    'repo': ('Depot', 'url'),
    'start': ('Debut', 'date'),
    'end': ('Fin', 'date'),
    'lots': ('Lots', 'number'),
    'estimateCost': ('Cout estime ($)', 'number'),
    'estimateDays': ('Duree estimee (jours)', 'number'),
    'realCost': ('Cout reel ($)', 'number'),
    'realDays': ('Duree reelle (jours)', 'number'),
    'summary': ('Resume', 'rich_text'),
    'po': ('PO', 'rich_text'),
}
SCHEMA = {
    'Nom': {'title': {}},
    'Statut': {'select': {'options': [{'name': s} for s in STATUSES]}},
    'Depot': {'url': {}},
    'Debut': {'date': {}},
    'Fin': {'date': {}},
    'Lots': {'number': {'format': 'number'}},
    'Cout estime ($)': {'number': {'format': 'dollar'}},
    'Duree estimee (jours)': {'number': {'format': 'number'}},
    'Cout reel ($)': {'number': {'format': 'dollar'}},
    'Duree reelle (jours)': {'number': {'format': 'number'}},
    'Resume': {'rich_text': {}},
    'PO': {'rich_text': {}},
}
TOKEN_FILE = os.environ.get('NOTION_TOKEN_FILE', '/run/notion/notion.env')


def token():
    """Read at each call, so a key entered by the owner takes effect without a restart."""
    try:
        with open(TOKEN_FILE, encoding='utf-8') as f:
            for line in f:
                if line.startswith('NOTION_TOKEN='):
                    return line.split('=', 1)[1].strip()
    except OSError:
        pass
    return ''


ID = re.compile(r'^[0-9a-f]{32}$|^[0-9a-f-]{36}$')
LOCK = threading.Lock()
STATE = {'db': None}


class BridgeError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def notion(method, path, body=None):
    request = urllib.request.Request(NOTION + path, method=method,
                                     data=None if body is None else json.dumps(body).encode(),
                                     headers={'Authorization': 'Bearer ' + token(),
                                              'Notion-Version': VERSION, 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read()).get('message', '')[:200]
        except (ValueError, OSError):
            detail = ''
        raise BridgeError(502, f'Notion HTTP {exc.code}: {detail}') from None
    except OSError as exc:
        raise BridgeError(502, f'Notion indisponible ({type(exc).__name__})') from None


def plain(rich):
    return ''.join(part.get('plain_text', '') for part in rich or [])


def search(kind, title):
    found = notion('POST', '/search', {'query': title, 'filter': {'property': 'object', 'value': kind}})
    out = []
    for item in found.get('results', []):
        if item.get('archived') or item.get('in_trash'):
            continue
        name = plain(item.get('title')) if kind == 'database' else plain(
            next((p.get('title') for p in item.get('properties', {}).values() if p.get('type') == 'title'), []))
        if name.strip() == title:
            out.append(item)
    return out


def database(create=False):
    with LOCK:
        if STATE['db']:
            return STATE['db']
        found = search('database', DB_TITLE)
        if len(found) > 1:
            raise BridgeError(409, f'Plusieurs bases "{DB_TITLE}" : en garder une seule')
        if found:
            props = found[0].get('properties', {})
            missing = {k: v for k, v in SCHEMA.items() if k not in props}
            options = {o.get('name') for o in (props.get('Statut', {}).get('select') or {}).get('options', [])}
            if 'Statut' in props and not set(STATUSES) <= options:  # statuses added later
                missing['Statut'] = SCHEMA['Statut']
            if missing:  # columns added after the database was created
                notion('PATCH', f"/databases/{found[0]['id']}", {'properties': missing})
            STATE['db'] = found[0]['id']
            return STATE['db']
        if not create:
            raise BridgeError(404, f'Base "{DB_TITLE}" absente : appeler POST /setup')
        parents = search('page', PARENT_TITLE)
        if len(parents) != 1:
            raise BridgeError(404, f'Page "{PARENT_TITLE}" introuvable ou en double : la connecter a l integration')
        db = notion('POST', '/databases', {'parent': {'type': 'page_id', 'page_id': parents[0]['id']},
                                          'title': [{'type': 'text', 'text': {'content': DB_TITLE}}],
                                          'properties': SCHEMA})
        STATE['db'] = db['id']
        return STATE['db']


def text(value):
    value = str(value)
    return [{'type': 'text', 'text': {'content': value[i:i + 1900]}} for i in range(0, min(len(value), 19000), 1900)]


def properties(fields, creating):
    out = {}
    for key, value in fields.items():
        if key not in FIELDS:
            raise BridgeError(400, f'Champ inconnu : {key}')
        prop, kind = FIELDS[key]
        if value is None:
            out[prop] = {kind: None} if kind in ('number', 'url', 'date', 'select') else {kind: []}
        elif kind == 'title' or kind == 'rich_text':
            out[prop] = {kind: text(value)}
        elif kind == 'select':
            if value not in STATUSES:
                raise BridgeError(400, f'Statut invalide (valeurs : {", ".join(STATUSES)})')
            out[prop] = {'select': {'name': value}}
        elif kind == 'number':
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise BridgeError(400, f'{key} doit etre un nombre')
            out[prop] = {'number': value}
        elif kind == 'date':
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', str(value)):
                raise BridgeError(400, f'{key} doit etre une date AAAA-MM-JJ')
            out[prop] = {'date': {'start': value}}
        elif kind == 'url':
            if not str(value).startswith('https://'):
                raise BridgeError(400, f'{key} doit etre une URL https')
            out[prop] = {'url': value}
    if creating and 'Nom' not in out:
        raise BridgeError(400, 'name est obligatoire')
    return out


def summary(page):
    props = page.get('properties', {})
    row = {'id': page['id'], 'url': page.get('url')}
    for key, (prop, kind) in FIELDS.items():
        value = props.get(prop, {})
        if kind in ('title', 'rich_text'):
            row[key] = plain(value.get(kind))
        elif kind == 'select':
            row[key] = (value.get('select') or {}).get('name')
        elif kind == 'date':
            row[key] = (value.get('date') or {}).get('start')
        else:
            row[key] = value.get(kind)
    return row


def owned_page(page_id):
    if not ID.match(page_id or ''):
        raise BridgeError(400, 'Identifiant de page invalide')
    page = notion('GET', f'/pages/{page_id}')
    parent = page.get('parent', {})
    if parent.get('type') != 'database_id' or parent.get('database_id', '').replace('-', '') != database().replace('-', ''):
        raise BridgeError(403, 'Cette page n appartient pas a la base des projets')
    return page


INLINE = re.compile(r'\*\*(.+?)\*\*|`([^`]+)`|\[([^\]]+)\]\((https://[^)\s]+)\)|(https://\S+)')
NUMBERED = re.compile(r'\d+[.)] ')
BULLET = ('- ', '* ', '• ')


def rich(value):
    """Inline Markdown (bold, code, https links) -> Notion rich text; anything else stays plain text."""
    value, out, pos = str(value)[:19000], [], 0
    for m in INLINE.finditer(value):
        if m.start() > pos:
            out += text(value[pos:m.start()])
        if m.group(1):
            out += [dict(t, annotations={'bold': True}) for t in text(m.group(1))]
        elif m.group(2):
            out += [dict(t, annotations={'code': True}) for t in text(m.group(2))]
        else:
            label, url = (m.group(3), m.group(4)) if m.group(3) else (m.group(5), m.group(5))
            out.append({'type': 'text', 'text': {'content': label[:1900], 'link': {'url': url}}})
        pos = m.end()
    if pos < len(value):
        out += text(value[pos:])
    return out or text('')


def node(kind, value):
    return {'object': 'block', 'type': kind, kind: {'rich_text': rich(value)}}


def convert(body):
    """Markdown subset -> Notion blocks: headings, bullets, numbered lists, tables, <details> toggles, paragraphs.
    Raw HTML is never interpreted: other tags stay visible as text."""
    lines, out, i = str(body or '').split('\n'), [], 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
        elif line.startswith('<details>'):
            j = i + 1
            summary = re.sub(r'</?summary>', '', lines[j].strip()) if j < len(lines) and '<summary>' in lines[j] else 'Details'
            k = j + 1
            while k < len(lines) and '</details>' not in lines[k]:
                k += 1
            toggle = node('toggle', summary)
            toggle['toggle']['children'] = convert('\n'.join(lines[j + 1:k]))
            out.append(toggle)
            i = k + 1
        elif line.startswith('#'):
            out.append(node('heading_3', line.lstrip('#').strip()))
            i += 1
        elif line.startswith('|'):
            rows = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                cells = [c.strip() for c in lines[i].strip().strip('|').split('|')]
                if not all(re.fullmatch(r':?-{2,}:?', c) for c in cells):
                    rows.append(cells)
                i += 1
            width = max(len(r) for r in rows)
            out.append({'object': 'block', 'type': 'table', 'table': {
                'table_width': width, 'has_column_header': True, 'has_row_header': False,
                'children': [{'object': 'block', 'type': 'table_row', 'table_row': {
                    'cells': [rich(r[c]) if c < len(r) else [] for c in range(width)]}} for r in rows]}})
        elif line.startswith(BULLET):
            out.append(node('bulleted_list_item', line[2:]))
            i += 1
        elif NUMBERED.match(line):
            out.append(node('numbered_list_item', NUMBERED.sub('', line, count=1)))
            i += 1
        else:
            para = [line]
            i += 1
            while i < len(lines) and lines[i].strip() and not lines[i].strip().startswith(('#', '|', '<details>') + BULLET) \
                    and not NUMBERED.match(lines[i].strip()):
                para.append(lines[i].strip())
                i += 1
            out.append(node('paragraph', ' '.join(para)))
    return out


def blocks(title, body):
    out = [{'object': 'block', 'type': 'heading_2', 'heading_2': {'rich_text': text(title)}}] + convert(body)
    if len(out) > 90:
        raise BridgeError(400, 'Section trop longue (90 blocs maximum)')
    return out


def handle(method, path, body):
    if method == 'GET' and path == '/projects':
        result = notion('POST', f'/databases/{database()}/query', {'page_size': 100})
        return 200, {'database': database(), 'projects': [summary(p) for p in result.get('results', [])]}
    if method == 'POST' and path == '/setup':
        return 200, {'database': database(create=True)}
    if method == 'POST' and path == '/projects':
        fields = body.get('fields') or {}
        name = str(fields.get('name') or '').strip()
        existing = notion('POST', f'/databases/{database()}/query',
                          {'filter': {'property': 'Nom', 'title': {'equals': name}}}).get('results', []) if name else []
        if existing:
            raise BridgeError(409, f'Le projet "{name}" existe deja (id {existing[0]["id"]}) : utiliser update')
        page = notion('POST', '/pages', {'parent': {'database_id': database()}, 'properties': properties(fields, True)})
        return 201, summary(page)
    match = re.fullmatch(r'/projects/([0-9a-f-]{32,36})(/sections)?', path)
    if match and method == 'PATCH' and not match.group(2):
        owned_page(match.group(1))
        page = notion('PATCH', f'/pages/{match.group(1)}', {'properties': properties(body.get('fields') or {}, False)})
        return 200, summary(page)
    if match and method == 'POST' and match.group(2):
        owned_page(match.group(1))
        title = str(body.get('title') or '').strip()
        if not title:
            raise BridgeError(400, 'title est obligatoire')
        notion('PATCH', f'/blocks/{match.group(1)}/children', {'children': blocks(title, body.get('text'))})
        return 200, {'ok': True}
    raise BridgeError(404, 'Route inconnue')


class Handler(BaseHTTPRequestHandler):
    server_version = 'notion-bridge'

    def log_message(self, fmt, *args):
        print('%s %s' % (self.command, fmt % args), flush=True)

    def reply(self, status, payload):
        raw = json.dumps(payload, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def route(self):
        if self.path == '/health':
            return self.reply(200, {'ok': True, 'configured': bool(token())})
        if self.headers.get('Authorization') != 'Bearer ' + os.environ['BRIDGE_KEY']:
            return self.reply(401, {'error': 'Cle du relais invalide'})
        if not token():
            return self.reply(503, {'error': 'Cle Notion absente : le proprietaire doit lancer set-notion-token.sh'})
        length = int(self.headers.get('Content-Length') or 0)
        if length > 200000:
            return self.reply(413, {'error': 'Requete trop grande'})
        try:
            body = json.loads(self.rfile.read(length) or b'{}') if length else {}
            if not isinstance(body, dict):
                raise ValueError
        except ValueError:
            return self.reply(400, {'error': 'JSON invalide'})
        try:
            status, payload = handle(self.command, self.path, body)
        except BridgeError as exc:
            status, payload = exc.status, {'error': str(exc)}
        self.reply(status, payload)

    do_GET = do_POST = do_PATCH = route


if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', 8080), Handler).serve_forever()
