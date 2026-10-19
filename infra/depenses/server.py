"""Owner-only, read-only D-012 page. Run behind local Tailscale Serve."""
from datetime import date, datetime, timedelta
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import secrets
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

PERIODS = {p: 'essai.depenses_par_' + p for p in ('semaine', 'mois', 'trimestre', 'annee')}


def parameters(query):
    args = parse_qs(query, strict_parsing=True, keep_blank_values=True, max_num_fields=3)
    if set(args) != {'periode', 'debut', 'variables'} or any(len(v) != 1 for v in args.values()):
        raise ValueError('parameters')
    period, raw, variables = (args[k][0] for k in ('periode', 'debut', 'variables'))
    if period not in PERIODS or variables not in ('0', '1') or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', raw):
        raise ValueError('parameters')
    start = date.fromisoformat(raw)
    if period == 'semaine':
        if start.weekday() != 0:
            raise ValueError('Monday required')
        end = start + timedelta(days=6)
    else:
        months = {'mois': 1, 'trimestre': 3, 'annee': 12}[period]
        if start.day != 1 or (start.month - 1) % months:
            raise ValueError('calendar boundary required')
        year, month = divmod(start.year * 12 + start.month - 1 + months, 12)
        end = date(year, month + 1, 1) - timedelta(days=1)
    return period, start, end, variables == '1'


def encode(value):
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError('nonfinite amount')
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError('unsupported database value')


def connect(dsn):
    import psycopg
    from psycopg.rows import dict_row
    return psycopg.connect(dsn, row_factory=dict_row, connect_timeout=5,
                           options='-c default_transaction_read_only=on -c statement_timeout=10000')


def read_data(dsn, params, connector=connect):
    period, start, end, variables = params
    with connector(dsn) as conn:
        with conn.cursor() as cur:
            cur.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            cur.execute('SELECT current_user AS role, current_database() AS database')
            identity = cur.fetchone()
            if identity != {'role': 'ledger_dorasso', 'database': 'comptabilite'}:
                raise ValueError('unexpected database identity')
            cur.execute('SELECT date_calcul, calcule_le, couverture FROM essai.depenses_calcul WHERE id = true')
            calculation = cur.fetchone()
            # Only the subcategory level is summed. Unknown amounts remain unknown.
            # Keep excluded groups visible even with the fixed-expense toggle.
            cte = f'''WITH selected AS (
                SELECT v.* FROM {PERIODS[period]} v
                WHERE periode_debut = %s AND niveau = 'sous_categorie'
                AND (NOT %s OR hors_total OR NOT debit_bancaire OR EXISTS (
                    SELECT 1 FROM essai.depenses_detail d
                    WHERE d.sous_categorie = v.sous_categorie
                    AND d.fixe_variable = 'variable'))
            ) '''
            aggregate = '''CASE WHEN count(*) = 0 OR count(total_cad) < count(*)
                THEN NULL ELSE sum(total_cad) END AS total_cad,
                sum(nombre_transactions) AS nombre_transactions,
                sum(montants_inconnus) AS montants_inconnus,
                sum(nombre_a_revoir) AS nombre_a_revoir'''
            cur.execute(cte + 'SELECT * FROM selected ORDER BY total_cad DESC NULLS LAST, famille, sous_categorie', (start, variables))
            subs = cur.fetchall()
            cur.execute(cte + 'SELECT famille, hors_total, debit_bancaire, ' + aggregate +
                        ' FROM selected GROUP BY famille, hors_total, debit_bancaire ORDER BY total_cad DESC NULLS LAST, famille', (start, variables))
            families = cur.fetchall()
            cur.execute(cte + 'SELECT ' + aggregate + ' FROM selected WHERE NOT hors_total AND debit_bancaire', (start, variables))
            total = cur.fetchone()
            cur.execute('''SELECT * FROM essai.depenses_detail
                WHERE (date_transaction BETWEEN %s AND %s OR date_transaction IS NULL)
                AND (NOT %s OR fixe_variable = 'variable' OR hors_total OR NOT debit_bancaire OR doublon OR date_transaction IS NULL)
                ORDER BY montant_cad DESC NULLS LAST, date_transaction, entite, qbo_id''', (start, end, variables))
            detail = cur.fetchall()
    return dict(periode=period, debut=start, fin=end, variables=variables,
                calcul=calculation, jour_attendu=datetime.now(ZoneInfo('America/Toronto')).date(), total=total,
                familles=families, sous_categories=subs, detail=detail,
                confirmation_bancaire=None, derniere_collecte=None)


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, login, dsn, port=3112, reader=read_data):
        if not login or not dsn:
            raise ValueError('ALLOWED_LOGIN and LEDGER_DSN required')
        self.login, self.dsn, self.reader = login, dsn, reader
        super().__init__(('127.0.0.1', port), Handler)


class Handler(BaseHTTPRequestHandler):
    server_version = 'depenses'

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, *args):
        pass  # No identities, financial data, DSNs or query strings in logs.

    def respond(self, code, body, mime='text/plain; charset=utf-8', nonce=None):
        data = body.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Security-Policy', "default-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'; connect-src 'self'" +
                         (f"; script-src 'nonce-{nonce}'; style-src 'nonce-{nonce}'" if nonce else ''))
        for key, value in [('Cache-Control', 'no-store'), ('X-Frame-Options', 'DENY'),
                           ('Referrer-Policy', 'same-origin'), ('X-Content-Type-Options', 'nosniff')]:
            self.send_header(key, value)
        if code == 405:
            self.send_header('Allow', 'GET')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(data)

    def allowed(self):
        if self.headers.get_all('Tailscale-User-Login') != [self.server.login]:
            self.respond(403, 'Accès réservé au propriétaire.')
            return False
        return True

    def send_error(self, code, message=None, explain=None):
        if code == 501:
            if self.allowed():
                self.respond(405, 'Méthode refusée.')
        else:
            self.respond(code, 'Requête refusée.')

    def do_GET(self):
        if not self.allowed():
            return
        try:
            url = urlsplit(self.path)
            if url.scheme or url.netloc or url.fragment:
                raise ValueError('URL')
            if url.path == '/depenses' and not url.query:
                nonce = secrets.token_urlsafe(24)
                page = Path(__file__).with_name('page.html').read_text(encoding='utf-8')
                return self.respond(200, page.replace('__NONCE__', nonce), 'text/html; charset=utf-8', nonce)
            if url.path != '/depenses/api':
                return self.respond(404, 'Page inconnue.')
            params = parameters(url.query)
        except (ValueError, OverflowError):
            return self.respond(400, 'Paramètres invalides.')
        try:
            result = self.server.reader(self.server.dsn, params)
            self.respond(200, json.dumps(result, default=encode, ensure_ascii=True, allow_nan=False), 'application/json; charset=utf-8')
        except Exception:
            self.respond(503, 'Lecture indisponible. Réessayez ultérieurement.')


if __name__ == '__main__':
    Server(os.environ['ALLOWED_LOGIN'], os.environ['LEDGER_DSN']).serve_forever()
