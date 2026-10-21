"""Offline tests: HTTP byte streams and a scripted database, no sockets."""
from datetime import date, datetime, timezone
from decimal import Decimal
import importlib.util
import io
import json
from pathlib import Path
import re
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('depenses_page', Path(__file__).with_name('server.py'))
page = importlib.util.module_from_spec(spec)
spec.loader.exec_module(page)

QUERY = 'periode=mois&debut=2026-10-01&variables=0'


class Transport:
    def __init__(self, data):
        self.input = io.BytesIO(data)
        self.output = bytearray()

    def makefile(self, *args):
        return self.input

    def sendall(self, data):
        self.output.extend(data)

    def settimeout(self, timeout):
        pass


class Database:
    def __init__(self, role='ledger_dorasso', database='comptabilite'):
        self.calls = []
        self.results = iter([
            {'role': role, 'database': database},
            {'date_calcul': date(2026, 10, 18), 'calcule_le': datetime(2026, 10, 18, tzinfo=timezone.utc), 'couverture': {'complete': False}},
            [{'total_cad': Decimal('0.100000000000000001')}],
            [{'famille': 'Frais & services', 'total_cad': Decimal('0.100000000000000001')}],
            {'total_cad': Decimal('0.100000000000000001'), 'nombre_transactions': 1},
            [{'marchand': '<img src=x onerror=alert(1)>', 'memo': '</script><script>alert(2)</script>', 'montant_cad': Decimal('0.100000000000000001')}],
        ])

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def cursor(self):
        return self

    def execute(self, sql, args=None):
        self.calls.append((sql, args))

    def fetchone(self):
        return next(self.results)

    fetchall = fetchone


class PageTests(unittest.TestCase):
    def request(self, method='GET', path='/depenses', identity='owner', reader=None):
        self.reader = reader or Mock(return_value={})
        server = SimpleNamespace(login='owner', dsn='secret-not-in-errors', reader=self.reader)
        headers = '' if identity is None else 'Tailscale-User-Login: ' + identity + '\r\n'
        sock = Transport(f'{method} {path} HTTP/1.1\r\nHost: local\r\n{headers}\r\n'.encode())
        page.Handler(sock, ('127.0.0.1', 1234), server)
        head, body = bytes(sock.output).split(b'\r\n\r\n', 1)
        lines = head.decode().split('\r\n')
        return int(lines[0].split()[1]), dict(line.split(': ', 1) for line in lines[1:]), body

    def test_identity_required_and_unique(self):
        for identity in (None, 'other', 'owner\r\nTailscale-User-Login: owner'):
            with self.subTest(identity=identity):
                status, headers, _ = self.request(identity=identity)
                self.assertEqual(status, 403)
                self.assertEqual(headers['Cache-Control'], 'no-store')
                self.reader.assert_not_called()

    def test_only_get(self):
        for method in ('POST', 'HEAD', 'PUT', 'PATCH', 'DELETE', 'OPTIONS', 'TRACE', 'CONNECT', 'CUSTOM'):
            with self.subTest(method=method):
                status, headers, body = self.request(method=method)
                self.assertEqual(status, 405)
                self.assertEqual(headers['Allow'], 'GET')
                self.reader.assert_not_called()
                if method == 'HEAD':
                    self.assertEqual(body, b'')
                self.assertEqual(self.request(method=method, identity=None)[0], 403)

    def test_invalid_parameters(self):
        queries = ['', QUERY + '&variables=1', QUERY + '&extra=x',
                   QUERY.replace('mois', 'month'), QUERY.replace('2026-10-01', '2026-02-30'),
                   QUERY.replace('2026-10-01', '2026-10-02'), QUERY.replace('variables=0', 'variables=2'),
                   QUERY.replace('2026-10-01', '26-10-01'), QUERY.replace('mois', 'semaine'),
                   'periode=annee&debut=2026-10-01&variables=0',
                   'periode=trimestre&debut=2026-11-01&variables=0',
                   'periode=mois&debut=9999-12-01&variables=0', QUERY + '&bad']
        for query in queries:
            with self.subTest(query=query):
                self.assertEqual(self.request(path='/depenses/api?' + query)[0], 400)
                self.reader.assert_not_called()

    def test_calendar_bounds(self):
        for period, start, end in [('semaine', '2026-08-31', '2026-09-06'),
                                   ('mois', '2024-02-01', '2024-02-29'),
                                   ('trimestre', '2026-10-01', '2026-12-31'),
                                   ('annee', '2026-01-01', '2026-12-31')]:
            parsed = page.parameters(f'periode={period}&debut={start}&variables=1')
            self.assertEqual(parsed[2].isoformat(), end)
            self.assertTrue(parsed[3])

    def test_page_nonce_and_no_unsafe_html_sinks(self):
        status, headers, body = self.request()
        self.assertEqual(status, 200)
        html = body.decode()
        nonce = re.search(r'<script nonce="([^"]+)"', html)[1]
        self.assertIn(f"script-src 'nonce-{nonce}'", headers['Content-Security-Policy'])
        self.assertIn(f'<style nonce="{nonce}">', html)
        self.assertNotIn(nonce.encode(), self.request()[2])
        for forbidden in ('innerHTML', 'outerHTML', 'insertAdjacentHTML', 'document.write', 'style=', 'onclick=', 'données fictives', 'fonts.googleapis.com', 'catégories revues'):
            self.assertNotIn(forbidden, html)
        self.assertIn('n.textContent=text', html)
        self.assertIn("node('strong',t.marchand", html)
        self.assertIn("merchant.append(node('span',[t.libelle_sous_categorie", html)
        self.assertEqual(headers['X-Frame-Options'], 'DENY')
        self.assertEqual(headers['Referrer-Policy'], 'same-origin')
        self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(int(headers['Content-Length']), len(body))

    def test_plain_language_and_two_column_table(self):
        html = self.request()[2].decode()
        for technical in ('classé provisoire', 'classement provisoire', 'essai',
                          'contrat de lecture', 'horodatage', 'n.d.'):
            self.assertNotIn(technical, html.lower())
        headings = re.findall(r'<th(?: class="amt")?>(.*?)</th>', html)
        self.assertEqual(headings, ['Nature', 'Montant'])
        self.assertIn("['Nature','Montant']", html)
        self.assertIn('td.colSpan=2', html)
        self.assertNotIn('overflow-x: auto', html)
        self.assertIn('Total des dépenses —', html)
        self.assertIn("state.sel=state.sel===f?null:f", html)

    def test_database_decimal_and_untrusted_text_transport(self):
        db = Database()
        with patch.object(page, 'ZoneInfo', return_value=timezone.utc):
            result = page.read_data('secret', page.parameters(QUERY), connector=lambda dsn: db)
        status, headers, body = self.request(path='/depenses/api?' + QUERY, reader=Mock(return_value=result))
        self.assertEqual(status, 200)
        self.assertEqual(headers['Content-Type'], 'application/json; charset=utf-8')
        decoded = json.loads(body)
        self.assertEqual(decoded['total']['total_cad'], '0.100000000000000001')
        self.assertEqual(decoded['detail'][0]['memo'], '</script><script>alert(2)</script>')
        self.assertEqual(decoded['detail'][0]['marchand'], '<img src=x onerror=alert(1)>')
        self.assertEqual(db.calls[0][0], 'SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        for sql, args in db.calls[3:6]:
            self.assertIn('essai.depenses_par_mois', sql)
            self.assertIn("niveau = 'sous_categorie'", sql)
            self.assertEqual(args, (date(2026, 10, 1), False))
        self.assertIn('count(total_cad) < count(*)', db.calls[5][0])
        self.assertIn('WHERE NOT hors_total AND debit_bancaire', db.calls[5][0])
        self.assertIn('ORDER BY montant_cad DESC NULLS LAST, date_transaction, entite, qbo_id', db.calls[-1][0])
        self.assertIn('OR date_transaction IS NULL', db.calls[-1][0])

    def test_wrong_database_identity(self):
        for db in (Database(role='ledger_essai'), Database(database='postgres')):
            with self.assertRaises(ValueError):
                page.read_data('secret', page.parameters(QUERY), connector=lambda dsn: db)
            self.assertEqual(len(db.calls), 2)

    def test_variable_filter_preserves_exceptions(self):
        db = Database()
        with patch.object(page, 'ZoneInfo', return_value=timezone.utc):
            page.read_data('secret', page.parameters(QUERY.replace('variables=0', 'variables=1')), connector=lambda dsn: db)
        self.assertTrue(db.calls[3][1][1])
        self.assertIn("d.fixe_variable = 'variable'", db.calls[3][0])
        self.assertIn('OR hors_total OR NOT debit_bancaire', db.calls[3][0])
        self.assertIn('OR doublon OR date_transaction IS NULL', db.calls[-1][0])

    def test_errors_do_not_leak_credentials(self):
        status, _, body = self.request(path='/depenses/api?' + QUERY, reader=Mock(side_effect=RuntimeError('secret-not-in-errors')))
        self.assertEqual(status, 503)
        self.assertNotIn(b'secret', body)
        self.assertEqual(self.request(path='/other')[0], 404)

    def test_null_and_decimal_encoding(self):
        self.assertEqual(json.dumps({'amount': None, 'exact': Decimal('12345678901234567890.1200')}, default=page.encode),
                         '{"amount": null, "exact": "12345678901234567890.1200"}')
        with self.assertRaises(ValueError):
            page.encode(Decimal('NaN'))

    def test_files_lf_without_bom(self):
        for path in [*Path(__file__).parent.glob('*.py'), Path(__file__).with_name('page.html'),
                     Path(__file__).with_name('README.md'), Path(__file__).parents[2] / 'ops/systemd/depenses.service']:
            raw = path.read_bytes()
            self.assertNotIn(b'\r', raw, str(path))
            self.assertFalse(raw.startswith(b'\xef\xbb\xbf'), str(path))


if __name__ == '__main__':
    unittest.main()
