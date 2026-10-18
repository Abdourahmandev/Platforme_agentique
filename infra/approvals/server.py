"""Approbations: the owner's approve / request-changes page for Paperclip tickets.

Paperclip 2026.1005.0 requires the approval decision and its comment in the same
PATCH, which its issue page does not send. This page lists the tickets waiting for
the owner's approval and sends both together. Served on 127.0.0.1 behind
`tailscale serve`, which adds the caller's Tailscale identity: only ALLOWED_LOGIN
may use it. Every form carries a one-time token; POSTs must come from this origin.
/secrets lets the owner enter a whitelisted key (Notion) from a phone: checked with
the provider, written 0600, never shown again nor logged.
Standard library only; the board token never leaves the server.
"""
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
import time
from urllib.parse import parse_qs, quote, urlparse
import urllib.error
import urllib.request

PRIVATE = Path(os.environ.get('LOCALAPPDATA') or Path.home() / '.local/share') / 'AsiaPaperclip'
API = 'http://127.0.0.1:3100/api'
ALLOWED_LOGIN = os.environ['ALLOWED_LOGIN']
PUBLIC_ORIGIN = os.environ['PUBLIC_ORIGIN'].rstrip('/')
PAPERCLIP_URL = os.environ['PAPERCLIP_URL'].rstrip('/')
FORM_TOKENS = {}  # one-time token -> (issue id, expiry)

STYLE = """
:root{--bg:#f6f7f9;--card:#fff;--text:#1d2330;--muted:#5d6675;--line:#dde1e7;--ok:#1f7a4d;--no:#a33a2a;--link:#2457c5}
@media (prefers-color-scheme:dark){:root{--bg:#14171c;--card:#1d2128;--text:#e7eaf0;--muted:#9aa3b2;--line:#2e333d;--ok:#3fa877;--no:#d0705f;--link:#7aa2f7}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:16px/1.5 system-ui,sans-serif}
main{max-width:760px;margin:0 auto;padding:20px 16px 48px}h1{font-size:1.4rem;margin:0 0 4px}
.sub{color:var(--muted);margin:0 0 20px}.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px;margin:0 0 16px}
.id{color:var(--muted);font-size:.9rem}h2{font-size:1.1rem;margin:2px 0 8px}a{color:var(--link)}
.report{white-space:pre-wrap;max-height:260px;overflow:auto;background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:10px;font-size:.9rem}
textarea{width:100%;min-height:90px;margin:10px 0;padding:10px;border-radius:8px;border:1px solid var(--line);background:var(--bg);color:var(--text);font:inherit}
.row{display:flex;gap:10px;flex-wrap:wrap}button{flex:1;min-width:140px;border:0;border-radius:8px;padding:12px;font:600 1rem system-ui;color:#fff;cursor:pointer}
.ok{background:var(--ok)}.no{background:var(--no)}.msg{padding:12px 14px;border-radius:8px;margin:0 0 16px;border:1px solid var(--line);background:var(--card)}
"""


def api(method, route, body=None):
    token = json.loads((PRIVATE / 'board-token.json').read_text())['token']
    request = urllib.request.Request(API + route, method=method, data=None if body is None else json.dumps(body).encode(),
                                     headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read()
        return json.loads(raw) if raw else None


def pending():
    company = json.loads((PRIVATE / 'company.json').read_text())['id']
    owner = json.loads((PRIVATE / 'owner.json').read_text())['userId']
    names = {a['id']: a['name'] for a in api('GET', f'/companies/{company}/agents')}
    rows = []
    for issue in api('GET', f'/companies/{company}/issues'):
        if issue.get('status') != 'in_review' or issue.get('assigneeUserId') != owner:
            continue
        comments = api('GET', f"/issues/{issue['id']}/comments")
        comments = sorted(comments.get('items', comments) if isinstance(comments, dict) else comments,
                          key=lambda c: c.get('createdAt', ''))
        reports = [c for c in comments if c.get('authorAgentId')]
        last = reports[-1] if reports else None
        rows.append({'issue': issue, 'author': names.get(last['authorAgentId']) if last else None,
                     'report': (last or {}).get('body', '')})
    return sorted(rows, key=lambda r: r['issue']['identifier'])


QBO_CALLBACK = '/qbo/callback'


class Handler(BaseHTTPRequestHandler):
    server_version = 'approbations'

    def log_message(self, fmt, *args):
        # The OAuth callback carries a one-time authorization code: never log its query.
        if urlparse(getattr(self, 'path', '')).path == QBO_CALLBACK:
            print('%s %s (requete masquee)' % (self.command, QBO_CALLBACK), flush=True)
            return
        print('%s %s' % (self.command, fmt % args), flush=True)

    def allowed(self):
        if self.headers.get('Tailscale-User-Login') != ALLOWED_LOGIN:
            self.respond(403, '<p>Acces reserve au proprietaire.</p>')
            return False
        return True

    def respond(self, code, body, location=None):
        page = (f'<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" '
                f'content="width=device-width,initial-scale=1"><title>Approbations</title><style>{STYLE}</style>'
                f'</head><body><main>{body}</main></body></html>').encode()
        self.send_response(code)
        if location:
            self.send_header('Location', location)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Security-Policy', "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'")
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Length', str(len(page)))
        self.end_headers()
        self.wfile.write(page)

    def qbo_callback(self):
        """Intuit OAuth redirect for Dorasso's QuickBooks connector (Decidata_accoutant #8).

        Shows the full redirect address for the owner to paste into the private terminal
        (connectors.quickbooks.owner authorize). Nothing is stored, logged or exchanged here.
        """
        address = PUBLIC_ORIGIN + self.path
        self.respond(200, '<h1>QuickBooks : autorisation recue</h1>'
                     "<p class=\"sub\">Copiez toute l'adresse ci-dessous et collez-la dans le terminal prive "
                     '(saisie masquee). Ne la partagez avec personne ; elle expire dans quelques minutes.</p>'
                     f'<textarea readonly rows="6" style="width:100%">{escape(address)}</textarea>')

    def do_GET(self):
        if not self.allowed():
            return
        message = parse_qs(urlparse(self.path).query).get('m', [''])[0][:200]
        now = time.time()
        for key in [k for k, (_, exp) in FORM_TOKENS.items() if exp < now]:
            FORM_TOKENS.pop(key, None)
        if urlparse(self.path).path == '/secrets':
            return self.secrets_page(message, now)
        if urlparse(self.path).path == QBO_CALLBACK:
            return self.qbo_callback()
        try:
            rows = pending()
        except (urllib.error.URLError, OSError) as exc:
            return self.respond(502, f'<p>Paperclip indisponible : {escape(str(exc))[:200]}</p>')
        html = ['<h1>Approbations</h1><p class="sub">Tickets Paperclip qui attendent votre decision.</p>']
        if message:
            html.append(f'<div class="msg">{escape(message)}</div>')
        if not rows:
            html.append('<div class="card">Rien a approuver pour le moment.</div>')
        for row in rows:
            issue = row['issue']
            token = secrets.token_urlsafe(24)
            FORM_TOKENS[token] = (issue['id'], now + 3600)
            link = f"{PAPERCLIP_URL}/issues/{escape(issue['identifier'])}"
            html.append(
                f'<div class="card"><div class="id">{escape(issue["identifier"])} · '
                f'<a href="{link}" target="_blank" rel="noopener">ouvrir dans Paperclip</a></div>'
                f'<h2>{escape(issue["title"])}</h2>'
                + (f'<div class="id">Dernier compte rendu : {escape(row["author"] or "?")}</div>'
                   f'<div class="report">{escape(row["report"][:6000])}</div>' if row['report'] else '')
                + f'<form method="post" action="/decide"><input type="hidden" name="t" value="{token}">'
                  f'<textarea name="comment" required placeholder="Votre commentaire de decision (obligatoire)"></textarea>'
                  f'<div class="row"><button class="ok" name="decision" value="approve">Approuver</button>'
                  f'<button class="no" name="decision" value="changes">Demander des modifications</button></div></form></div>')
        self.respond(200, ''.join(html))

    def do_POST(self):
        if not self.allowed():
            return
        origin = self.headers.get('Origin') or ''
        if origin and origin.rstrip('/') != PUBLIC_ORIGIN:
            return self.respond(403, '<p>Origine refusee.</p>')
        length = int(self.headers.get('Content-Length') or 0)
        if self.path not in ('/decide', '/secrets') or not 0 < length <= 20000:
            return self.respond(400, '<p>Requete invalide.</p>')
        form = parse_qs(self.rfile.read(length).decode())
        if self.path == '/secrets':
            return self.save_secret(form)
        token = form.get('t', [''])[0]
        issue_id, expiry = FORM_TOKENS.pop(token, (None, 0))
        decision = form.get('decision', [''])[0]
        comment = form.get('comment', [''])[0].strip()
        if not issue_id or expiry < time.time() or decision not in ('approve', 'changes') or not comment:
            return self.respond(303, '', location='/?m=' + quote('Formulaire expire ou incomplet : rechargez la page.'))
        status = 'done' if decision == 'approve' else 'in_progress'
        try:
            issue = api('PATCH', f'/issues/{issue_id}', {'status': status, 'comment': comment})
            note = f"{issue.get('identifier', 'Ticket')} : " + ('approuve.' if decision == 'approve' else 'renvoye pour modifications.')
        except urllib.error.HTTPError as exc:
            note = f'Paperclip a refuse la decision (HTTP {exc.code}).'
        self.respond(303, '', location='/?m=' + quote(note))

    def secrets_page(self, message, now):
        html = ['<h1>Secrets</h1><p class="sub">Entrer une cle sur le serveur depuis votre telephone. '
                'Elle est verifiee, enregistree en mode 0600, puis jamais reaffichee.</p>']
        if message:
            html.append(f'<div class="msg">{escape(message)}</div>')
        for name, target in SECRET_TARGETS.items():
            token = secrets.token_urlsafe(24)
            FORM_TOKENS[token] = ('secret:' + name, now + 900)
            state = 'enregistree' if target['file'].exists() else 'absente'
            html.append(f'<div class="card"><h2>{escape(target["label"])}</h2><div class="id">Etat : cle {state}</div>'
                        f'<form method="post" action="/secrets"><input type="hidden" name="t" value="{token}">'
                        f'<input type="hidden" name="target" value="{escape(name)}">'
                        f'<textarea name="value" required autocomplete="off" autocapitalize="off" spellcheck="false" '
                        f'placeholder="{escape(target["hint"])}"></textarea>'
                        f'<div class="row"><button class="ok">Verifier et enregistrer</button></div></form></div>')
        self.respond(200, ''.join(html))

    def save_secret(self, form):
        token = form.get('t', [''])[0]
        purpose, expiry = FORM_TOKENS.pop(token, (None, 0))
        name = form.get('target', [''])[0]
        value = form.get('value', [''])[0].strip()
        target = SECRET_TARGETS.get(name)
        if not target or purpose != 'secret:' + name or expiry < time.time() or not value:
            return self.respond(303, '', location='/secrets?m=' + quote('Formulaire expire ou incomplet : rechargez la page.'))
        try:
            who = target['check'](value)
        except ValueError as exc:
            return self.respond(303, '', location='/secrets?m=' + quote(str(exc)))
        target['file'].parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        tmp = target['file'].with_suffix('.tmp')
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as f:
            f.write(target['format'](value))
        os.replace(tmp, target['file'])
        self.respond(303, '', location='/secrets?m=' + quote(f'{target["label"]} : cle enregistree ({who}).'))


def check_notion(value):
    if not re.fullmatch(r'(ntn_|secret_)[A-Za-z0-9_]{20,200}', value):
        raise ValueError('Cle refusee : une cle Notion (ntn_...) est attendue.')
    request = urllib.request.Request('https://api.notion.com/v1/users/me', headers={
        'Authorization': 'Bearer ' + value, 'Notion-Version': '2022-06-28'})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return 'integration ' + (json.loads(response.read()).get('name') or '?')
    except urllib.error.HTTPError as exc:
        raise ValueError(f'Notion a refuse la cle (HTTP {exc.code}).') from None
    except OSError:
        raise ValueError('Notion injoignable : reessayez.') from None


def check_jev(value):
    # Format check only: the provider check is added once the official Jev API is documented (pilot design).
    if not re.fullmatch(r'[A-Za-z0-9_\-.]{20,300}', value):
        raise ValueError('Cle refusee : une cle d API sans espace, de 20 a 300 caracteres, est attendue.')
    return 'format verifie ; verification aupres de TypeSafe a la conception du pilote'


# Whitelisted secrets the owner may set from this page; nothing else is writable.
SECRET_TARGETS = {
    'notion': {'label': 'Notion (connexion « Asia (Decidata) »)', 'hint': 'Collez la cle ntn_...',
               'file': PRIVATE.parent / 'Notion/notion.env', 'check': check_notion,
               'format': lambda v: f'NOTION_TOKEN={v}\n'},
    'jev': {'label': 'Jev (TypeSafe AI, pilote Vitrine)', 'hint': 'Collez la cle d API Jev',
            'file': PRIVATE.parent / 'Jev/jev.env', 'check': check_jev,
            'format': lambda v: f'JEV_API_KEY={v}\n'},
}


if __name__ == '__main__':
    ThreadingHTTPServer(('127.0.0.1', int(os.environ.get('PORT', '3110'))), Handler).serve_forever()
