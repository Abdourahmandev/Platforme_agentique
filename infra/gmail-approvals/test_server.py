import base64
import hashlib
import http.client
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import tempfile
import threading
import time
import unittest
from zoneinfo import ZoneInfoNotFoundError
from unittest.mock import patch
from urllib.parse import urlencode, parse_qs


def module(name):
    spec = importlib.util.spec_from_file_location('gmail_' + name, Path(__file__).with_name(name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


page = module('server')
notification = module('notify')


class FakeGate:
    def __init__(self, path):
        self.calls = []
        self.payload = b'<html>attachment</html>'
        raw = b'From: owner@example.org\r\n\r\nimmutable MIME\r\n'
        self.item = {'id': 'draft-1', 'created_at': time.time(), 'expires_at': time.time() + 300,
                     'status': 'pending', 'sha256': hashlib.sha256(raw).hexdigest(),
                     'raw': base64.urlsafe_b64encode(raw).decode().rstrip('='),
                     'recipients': [['to', 'a@example.org'], ['cc', 'b@example.org']],
                     'subject': '<img src=x>', 'body': '<script>alert("bad")</script>\n& full body',
                     'attachments': [{'filename': 'test"\r\n.html', 'content_type': 'text/html',
                                      'size': len(self.payload), 'sha256': hashlib.sha256(self.payload).hexdigest(),
                                      'base64': base64.b64encode(self.payload).decode()}]}
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.bind(path)
        self.sock.listen()
        self.sock.settimeout(0.1)
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.run)
        self.thread.start()

    def run(self):
        while not self.stop.is_set():
            try:
                conn, _ = self.sock.accept()
            except socket.timeout:
                continue
            with conn:
                conn.settimeout(2)
                with conn.makefile('rb') as stream:
                    request = json.loads(stream.readline(262144))
                self.calls.append(request)
                result = self.item if request['op'] == 'read' else {
                    'id': request['id'], 'status': 'approved_dry_run' if request['op'] == 'approve' else 'deleted'}
                conn.sendall(json.dumps({'ok': True, 'result': result}).encode() + b'\n')

    def close(self):
        self.stop.set()
        self.thread.join(3)
        self.sock.close()


class PageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / 'api.sock')
        # Exercise the same framing/HTTP assertions on Windows too. Linux always
        # uses a real Unix socket; this fallback does not validate Unix access.
        if not hasattr(socket, 'AF_UNIX'):
            family_patch = patch.object(socket, 'AF_UNIX', socket.AF_INET, create=True)
            family_patch.start()
            self.addCleanup(family_patch.stop)
            self.path = ('127.0.0.1', 0)
        self.gate = FakeGate(self.path)
        if isinstance(self.path, tuple):
            self.path = self.gate.sock.getsockname()
        self.server = page.Server('owner@example.org', self.path, 0)
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.start()
        # Windows may lack the system IANA database; Linux deployment uses tzdata.
        try:
            page.ZoneInfo('America/Toronto')
        except ZoneInfoNotFoundError:
            from datetime import timezone, timedelta
            self.zone_patch = patch.object(page, 'ZoneInfo', return_value=timezone(timedelta(hours=-4), 'EDT'))
            self.zone_patch.start()
            self.addCleanup(self.zone_patch.stop)

    def tearDown(self):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()
        self.gate.close()
        self.tmp.cleanup()

    def request(self, method='GET', path='/gmail/draft-1', form=None, identity=True, origin=page.PUBLIC_ORIGIN):
        headers = {}
        if identity:
            headers['Tailscale-User-Login'] = 'owner@example.org'
        if method == 'POST':
            headers['Content-Type'] = 'application/x-www-form-urlencoded'
            if origin is not None:
                headers['Origin'] = origin
        conn = http.client.HTTPConnection(*self.server.server_address, timeout=3)
        try:
            conn.request(method, path, urlencode(form or {}) if method == 'POST' else None, headers)
            response = conn.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            conn.close()

    def form(self, action='approve'):
        status, _, body = self.request()
        self.assertEqual(status, 200)
        forms = re.findall(r'<form.*?</form>', body.decode())
        form = next(value for value in forms if '/' + action + '"' in value)
        return dict(re.findall(r'name="([^"]+)" value="([^"]+)"', form))

    def test_identity_required_on_all_routes(self):
        for method, path in [('GET', '/gmail/draft-1'), ('GET', '/gmail/draft-1/piece/' + 'a' * 64),
                             ('POST', '/gmail/draft-1/approve'), ('POST', '/gmail/draft-1/delete')]:
            self.assertEqual(self.request(method, path, identity=False)[0], 403)
        self.assertEqual(self.gate.calls, [])

    def test_missing_csrf(self):
        self.assertEqual(self.request('POST', '/gmail/draft-1/approve', {'sha256': 'a' * 64})[0], 403)
        self.assertEqual(self.gate.calls, [])

    def test_exact_fingerprint_and_replay(self):
        form = self.form()
        status, _, body = self.request('POST', '/gmail/draft-1/approve', form)
        self.assertEqual(status, 200)
        self.assertIn('approuvé, non envoyé (examen à blanc)', body.decode())
        self.assertEqual(self.gate.calls[-1], {'op': 'approve', 'id': 'draft-1', 'sha256': self.gate.item['sha256']})
        self.assertEqual(self.request('POST', '/gmail/draft-1/approve', form)[0], 403)
        self.assertEqual(sum(c['op'] == 'approve' for c in self.gate.calls), 1)

    def test_wrong_id_hash_action_and_origin(self):
        for path, sha, origin in [('/gmail/other/approve', None, page.PUBLIC_ORIGIN),
                                  ('/gmail/draft-1/approve', 'f' * 64, page.PUBLIC_ORIGIN),
                                  ('/gmail/draft-1/delete', None, page.PUBLIC_ORIGIN),
                                  ('/gmail/draft-1/approve', None, 'https://evil.example')]:
            form = self.form()
            if sha:
                form['sha256'] = sha
            self.assertEqual(self.request('POST', path, form, origin=origin)[0], 403)
        self.assertTrue(all(c['op'] == 'read' for c in self.gate.calls))

    def test_expired_token(self):
        form = self.form()
        entry = self.server.tokens[form['t']]
        self.server.tokens[form['t']] = (*entry[:3], 0)
        self.assertEqual(self.request('POST', '/gmail/draft-1/approve', form)[0], 403)

    def test_delete_contract(self):
        self.assertEqual(self.request('POST', '/gmail/draft-1/delete', self.form('delete'))[0], 200)
        self.assertEqual(self.gate.calls[-1], {'op': 'delete', 'id': 'draft-1'})

    def test_escaped_complete_preview_security_and_get_read_only(self):
        status, headers, body = self.request()
        text = body.decode()
        self.assertEqual(status, 200)
        self.assertIn('&lt;script&gt;alert(&quot;bad&quot;)&lt;/script&gt;', text)
        self.assertNotIn('<script>alert', text)
        self.assertIn('&lt;img src=x&gt;', text)
        for value in ['a@example.org', 'b@example.org', 'full body', 'Toronto', self.gate.item['sha256'],
                      self.gate.item['attachments'][0]['sha256']]:
            self.assertIn(value, text)
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertEqual(headers['X-Frame-Options'], 'DENY')
        self.assertEqual(headers['Referrer-Policy'], 'no-referrer')
        self.assertIn("default-src 'none'", headers['Content-Security-Policy'])
        for action in ('approve', 'delete'):
            self.assertEqual(self.request(path='/gmail/draft-1/' + action)[0], 404)
        self.assertEqual(self.gate.calls, [{'op': 'read', 'id': 'draft-1'}])

    def test_attachment_download(self):
        status, headers, body = self.request(path='/gmail/draft-1/piece/' + self.gate.item['attachments'][0]['sha256'])
        self.assertEqual(status, 200)
        self.assertEqual(body, self.gate.payload)
        self.assertEqual(headers['Content-Type'], 'application/octet-stream')
        self.assertTrue(headers['Content-Disposition'].startswith('attachment;'))
        self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(self.gate.calls, [{'op': 'read', 'id': 'draft-1'}])

    def test_bad_snapshot_and_response_bound(self):
        self.gate.item['sha256'] = '0' * 64
        self.assertEqual(self.request()[0], 502)
        with patch.object(page, 'MAX_RESPONSE', 100):
            self.assertEqual(self.request()[0], 502)

    def test_token_consumption_atomic(self):
        token = self.server.issue('draft-1', 'a' * 64, 'approve')
        results = []
        workers = [threading.Thread(target=lambda: results.append(self.server.consume(token, 'draft-1', 'a' * 64, 'approve'))) for _ in range(12)]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join()
        self.assertEqual(sum(results), 1)


class NotificationTests(unittest.TestCase):
    def test_plain_text_configured_owner_and_timeout(self):
        item = {'recipients': [['to', 'a@example.org']], 'subject': '<b>subject</b>',
                'summary': 'x' * 600, 'url': page.PUBLIC_ORIGIN + '/gmail/draft-1',
                'TELEGRAM_BOT_TOKEN': 'evil', 'TELEGRAM_OWNER_ID': '999'}
        with patch.dict(os.environ, TELEGRAM_BOT_TOKEN='123:secret', TELEGRAM_OWNER_ID='456'), \
                patch.object(notification.urllib.request, 'build_opener') as factory:
            factory.return_value.open.return_value.__enter__.return_value.read.return_value = b'{"ok":true}'
            notification.notify(item)
            args, kwargs = factory.return_value.open.call_args
            self.assertEqual(kwargs['timeout'], 5)
            self.assertIn('/bot123:secret/', args[0].full_url)
            data = parse_qs(args[0].data.decode())
            self.assertEqual(data['chat_id'], ['456'])
            self.assertNotIn('parse_mode', data)
            self.assertNotIn('reply_markup', data)
            self.assertIn('<b>subject</b>', data['text'][0])
            self.assertIn(item['url'], data['text'][0])
            self.assertIn('à approuver dans les 5 minutes sur la page', data['text'][0])

    def test_exception_has_no_secret_or_context(self):
        with patch.dict(os.environ, TELEGRAM_BOT_TOKEN='123:secret', TELEGRAM_OWNER_ID='456'), \
                patch.object(notification.urllib.request, 'build_opener', side_effect=RuntimeError('secret')):
            with self.assertRaises(RuntimeError) as caught:
                notification.notify({'recipients': [], 'subject': '', 'summary': '', 'url': ''})
        self.assertNotIn('secret', str(caught.exception))
        self.assertIsNone(caught.exception.__context__)


if __name__ == '__main__':
    unittest.main()
