"""Owner-only Gmail decisions, behind Tailscale Serve. Standard library only."""
import base64
from datetime import datetime
import hashlib
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import re
import secrets
import socket
import threading
import time
from urllib.parse import parse_qs, quote
from zoneinfo import ZoneInfo

PUBLIC_ORIGIN = 'https://rass-server.taild656dc.ts.net:8443'
SOCKET_PATH = '/run/dorasso-approvals/api.sock'
MAX_RESPONSE = 64 * 1024 * 1024
ROUTE = re.compile(r'/gmail/([A-Za-z0-9_-]{1,128})(?:/(approve|delete)|/piece/([a-f0-9]{64}))?')
SHA = re.compile(r'[a-f0-9]{64}')


class GateError(Exception):
    pass


def gate(path, request):
    """One bounded exchange, absolute deadline, no mutation retries."""
    deadline = time.monotonic() + 5
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(5)
        sock.connect(path)
        sock.settimeout(max(0.001, deadline - time.monotonic()))
        sock.sendall(json.dumps(request).encode() + b'\n')
        data = bytearray()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise GateError('unavailable')
            sock.settimeout(remaining)
            chunk = sock.recv(min(65536, MAX_RESPONSE + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > MAX_RESPONSE:
                raise GateError('invalid_response')
        if not data.endswith(b'\n') or b'\n' in data[:-1]:
            raise GateError('invalid_response')
        reply = json.loads(data)
        if reply.get('ok') is not True:
            # Never echo arbitrary transport errors or exception text.
            code = reply.get('error')
            raise GateError(code if code in ('expired', 'draft_changed', 'not_found',
                            'already_final', 'fingerprint_mismatch') else 'refused')
        return reply['result']


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, login, socket_path=SOCKET_PATH, port=3111):
        if not login:
            raise ValueError('ALLOWED_LOGIN required')
        self.login, self.socket_path = login, socket_path
        self.tokens = {}
        self.token_lock = threading.Lock()
        super().__init__(('127.0.0.1', port), Handler)

    def issue(self, item_id, sha, action):
        with self.token_lock:
            now = time.monotonic()
            self.tokens = {k: v for k, v in self.tokens.items() if v[3] > now}
            if len(self.tokens) >= 4096:
                self.tokens.pop(next(iter(self.tokens)))
            token = secrets.token_urlsafe(32)
            self.tokens[token] = (item_id, sha, action, now + 300)
            return token

    def consume(self, token, item_id, sha, action):
        with self.token_lock:
            entry = self.tokens.pop(token, None)
        return entry is not None and entry[:3] == (item_id, sha, action) and entry[3] > time.monotonic()


class Handler(BaseHTTPRequestHandler):
    server_version = 'gmail-approvals'

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, fmt, *args):
        # No URLs, request bodies, identities, tokens or email content.
        pass

    def send_error(self, code, message=None, explain=None):
        self.respond(code, '<p>Requête refusée.</p>')

    def respond(self, code, body, nonce=None, filename=None):
        if filename is None:
            body = ('<!doctype html><html lang="fr"><meta charset="utf-8">'
                    '<meta name="viewport" content="width=device-width,initial-scale=1">'
                    '<title>Accord Gmail</title><body>' + body + '</body></html>').encode()
        self.send_response(code)
        self.send_header('Content-Type', 'text/html; charset=utf-8' if filename is None else 'application/octet-stream')
        if filename is not None:
            self.send_header('Content-Disposition', "attachment; filename=\"piece\"; filename*=UTF-8''" + quote(filename, safe=''))
        self.send_header('Content-Security-Policy', "default-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'" +
                         ("; script-src 'nonce-" + nonce + "'" if nonce else ''))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def allowed(self):
        if self.headers.get_all('Tailscale-User-Login') != [self.server.login]:
            self.respond(403, '<p>Accès réservé au propriétaire.</p>')
            return False
        return True

    def do_GET(self):
        if not self.allowed():
            return
        route = ROUTE.fullmatch(self.path)
        if not route or route[2]:
            return self.respond(404, '<p>Page inconnue.</p>')
        try:
            item = gate(self.server.socket_path, {'op': 'read', 'id': route[1]})
            if route[3]:
                for piece in item['attachments']:
                    if piece['sha256'] == route[3]:
                        data = base64.b64decode(piece['base64'], validate=True)
                        if hashlib.sha256(data).hexdigest() != route[3] or len(data) != piece['size']:
                            raise ValueError('piece')
                        return self.respond(200, data, filename=piece['filename'])
                return self.respond(404, '<p>Pièce inconnue.</p>')
            self.show_item(route[1], item)
        except (GateError, OSError, ValueError, KeyError, TypeError):
            self.respond(502, '<p>Lecture impossible. Aucune décision transmise.</p>')

    def show_item(self, item_id, item):
        sha = item['sha256']
        if not SHA.fullmatch(sha):
            raise ValueError('sha256')
        raw = base64.b64decode(item['raw'] + '=' * (-len(item['raw']) % 4), altchars=b'-_', validate=True)
        if hashlib.sha256(raw).hexdigest() != sha:
            raise ValueError('snapshot')
        expires = float(item['expires_at'])
        date = datetime.fromtimestamp(expires, ZoneInfo('America/Toronto'))
        nonce = secrets.token_urlsafe(24)
        parts = ['<h1>Accord Gmail</h1>', f'<p>Statut : {escape(item["status"])}</p>',
                 f'<p>Échéance (Toronto) : {date:%Y-%m-%d %H:%M:%S %Z} — '
                 f'<span id="remaining">{max(0, int(expires - time.time()))} secondes</span></p>']
        for kind, label in (('to', 'To'), ('cc', 'Cc')):
            parts.append(f'<h2>{label}</h2><ul>' + ''.join('<li>' + escape(address) + '</li>'
                         for field, address in item['recipients'] if field == kind) + '</ul>')
        parts.extend([f'<h2>Objet</h2><pre>{escape(item["subject"])}</pre>',
                      f'<h2>Corps complet</h2><pre>{escape(item["body"])}</pre>', '<h2>Pièces</h2><ul>'])
        for piece in item['attachments']:
            if not SHA.fullmatch(piece['sha256']):
                raise ValueError('piece sha256')
            parts.append(f'<li>{escape(piece["filename"])} — {escape(piece["content_type"])} — '
                         f'{int(piece["size"])} octets — SHA-256 : {piece["sha256"]} '
                         f'<a href="/gmail/{item_id}/piece/{piece["sha256"]}">Télécharger</a></li>')
        parts.append(f'</ul><p>SHA-256 du MIME : <code>{sha}</code></p>')
        for action, label in (('approve', 'Approuver'), ('delete', 'Supprimer')):
            token = self.server.issue(item_id, sha, action)
            enabled = (item['status'] == 'pending' and expires > time.time()) if action == 'approve' else item['status'] in ('pending', 'approved_dry_run')
            parts.append(f'<form method="post" action="/gmail/{item_id}/{action}">'
                         f'<input type="hidden" name="t" value="{token}">'
                         f'<input type="hidden" name="sha256" value="{sha}">'
                         f'<button{"" if enabled else " disabled"}>{label}</button></form>')
        parts.append(f'<script nonce="{nonce}">const end={int(expires * 1000)};'
                     'function tick(){document.getElementById("remaining").textContent='
                     'Math.max(0,Math.ceil((end-Date.now())/1000))+" secondes";}tick();setInterval(tick,1000);</script>')
        self.respond(200, ''.join(parts), nonce=nonce)

    def do_POST(self):
        if not self.allowed():
            return
        # Like the existing page, tolerate absent Origin; tokens remain mandatory.
        origins = self.headers.get_all('Origin') or []
        if origins and (len(origins) != 1 or origins[0].rstrip('/') != PUBLIC_ORIGIN):
            return self.respond(403, '<p>Origine refusée.</p>')
        route = ROUTE.fullmatch(self.path)
        try:
            lengths = self.headers.get_all('Content-Length') or []
            if len(lengths) != 1 or self.headers.get('Transfer-Encoding'):
                raise ValueError('length')
            length = int(lengths[0])
            if not route or not route[2] or not 0 < length <= 4096 or self.headers.get_content_type() != 'application/x-www-form-urlencoded':
                raise ValueError('form')
            form = parse_qs(self.rfile.read(length).decode('utf-8'), strict_parsing=True, max_num_fields=2)
            if set(form) != {'t', 'sha256'} or any(len(v) != 1 for v in form.values()):
                raise ValueError('fields')
        except (ValueError, OSError):
            return self.respond(403, '<p>Formulaire invalide.</p>')
        sha = form['sha256'][0]
        if not self.server.consume(form['t'][0], route[1], sha, route[2]):
            return self.respond(403, '<p>Formulaire expiré ou déjà utilisé. Rechargez la page.</p>')
        request = {'op': route[2], 'id': route[1]}
        if route[2] == 'approve':
            request['sha256'] = sha
        try:
            result = gate(self.server.socket_path, request)
            message = {'approved_dry_run': 'approuvé, non envoyé (examen à blanc)',
                       'sent': 'envoyé', 'deleted': 'supprimé'}.get(result['status'], 'État à vérifier sur la page.')
            self.respond(200, '<p>' + message + '</p>')
        except GateError as exc:
            if str(exc) in ('unavailable', 'invalid_response'):
                return self.respond(502, '<p>Résultat inconnu : consultez le statut. Aucun réessai automatique.</p>')
            message = ('Brouillon modifié : créez un nouveau brouillon et une nouvelle demande.'
                       if str(exc) == 'draft_changed' else 'Décision refusée. Consultez le statut de la demande.')
            self.respond(409, '<p>' + message + '</p>')
        except (OSError, ValueError, KeyError, TypeError):
            self.respond(502, '<p>Résultat inconnu : consultez le statut. Aucun réessai automatique.</p>')


if __name__ == '__main__':
    Server(os.environ['ALLOWED_LOGIN']).serve_forever()
