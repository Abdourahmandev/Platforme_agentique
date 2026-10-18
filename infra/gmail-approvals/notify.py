"""Trusted host callback: credentials come exclusively from systemd environment."""
import json
import os
import re
import urllib.parse
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def short(value, limit):
    text = str(value)
    return text if len(text) <= limit else text[:limit - 1] + '…'


def notify(item):
    """Raise only a fixed, secret-free error so the host records notified:false."""
    failed = False
    try:
        token = os.environ['TELEGRAM_BOT_TOKEN']
        owner = os.environ['TELEGRAM_OWNER_ID']
        if not re.fullmatch(r'[0-9]+:[A-Za-z0-9_-]+', token) or not owner.isdecimal():
            raise ValueError('configuration')
        recipients = ', '.join(f'{kind}: {address}' for kind, address in item['recipients'])
        text = (f'Destinataires : {short(recipients, 1400)}\n'
                f'Objet : {short(item["subject"], 512)}\n'
                f'Résumé : {short(item["summary"], 350)}\n'
                f'{short(item["url"], 512)}\n'
                'à approuver dans les 5 minutes sur la page')
        body = urllib.parse.urlencode({'chat_id': owner, 'text': text,
                                      'disable_web_page_preview': 'true'}).encode()
        request = urllib.request.Request('https://api.telegram.org/bot' + token + '/sendMessage',
                                         data=body, headers={'Content-Type': 'application/x-www-form-urlencoded'})
        # No proxy credentials from the process environment; no cross-host redirects.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        with opener.open(request, timeout=5) as response:
            # One bounded read, no unbounded JSON load or streaming retry.
            data = response.read(65537)
            if len(data) > 65536 or json.loads(data).get('ok') is not True:
                raise ValueError('response')
    except Exception:
        failed = True
    # Outside the except block: no secret-bearing exception context survives.
    if failed:
        raise RuntimeError('Notification Telegram impossible.')
