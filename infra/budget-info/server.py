"""Read-only AI budget summary for Dorasso (GET / -> French text, GET /json -> JSON).

Holds the LiteLLM master key and the DeepSeek key; returns only figures, never a
key. Reachable from Dorasso on the internal `personal` network. Sources:
LiteLLM team/key spend and caps, LiteLLM spend per model (Gemini vs DeepSeek),
and DeepSeek's balance API. Gemini prepaid credit has no public balance API:
the summary says so and points to AI Studio. Cached 60 s.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import time
import urllib.request

LITELLM = os.environ.get('LITELLM_URL', 'http://litellm:4000')
TEAMS = {'asia-platform-staging': 'Equipe Decidata', 'dorasso-personnel': 'Dorasso (personnel)'}
CACHE = {'at': 0.0, 'data': None}


def get(url, key):
    request = urllib.request.Request(url, headers={'Authorization': 'Bearer ' + key})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read())


def collect():
    master, deepseek = os.environ['LITELLM_MASTER_KEY'], os.environ.get('DEEPSEEK_API_KEY', '')
    data = {'generated_at': time.strftime('%Y-%m-%d %H:%M %Z'), 'teams': [], 'providers': {}, 'deepseek_balance': None}
    for team_id, label in TEAMS.items():
        info = get(f'{LITELLM}/team/info?team_id={team_id}', master)
        team = info.get('team_info', {})
        data['teams'].append({
            'name': label, 'spend': round(team.get('spend') or 0, 2), 'max_budget': team.get('max_budget'),
            'reset': str(team.get('budget_reset_at') or '')[:10],
            'keys': sorted(({'name': k.get('key_alias'), 'spend': round(k.get('spend') or 0, 2),
                             'max_budget': k.get('max_budget')} for k in info.get('keys', [])),
                           key=lambda k: -k['spend'])})
    for row in get(f'{LITELLM}/global/spend/models', master):
        provider = str(row.get('model', '')).split('/')[0] or 'autre'
        data['providers'][provider] = round(data['providers'].get(provider, 0) + (row.get('total_spend') or 0), 2)
    if deepseek:
        try:
            balance = get('https://api.deepseek.com/user/balance', deepseek)
            usd = [b for b in balance.get('balance_infos', []) if b.get('currency') == 'USD'] or balance.get('balance_infos', [])
            if usd:
                data['deepseek_balance'] = {'currency': usd[0].get('currency'), 'total': usd[0].get('total_balance'),
                                            'available': balance.get('is_available')}
        except OSError as exc:
            data['deepseek_balance'] = {'error': type(exc).__name__}
    return data


def text(data):
    lines = [f"Budgets IA au {data['generated_at']}", '']
    for team in data['teams']:
        cap = team['max_budget']
        left = f", reste {round(cap - team['spend'], 2)} $" if cap else ''
        lines.append(f"{team['name']} : {team['spend']} $ depenses sur {cap} $ par 30 jours{left} (remise a zero le {team['reset']}).")
        for key in team['keys']:
            lines.append(f"  - {key['name']} : {key['spend']} $ sur {key['max_budget']} $")
    lines += ['', 'Depenses cumulees par fournisseur (suivies par LiteLLM) : '
              + ', '.join(f'{p} {v} $' for p, v in sorted(data['providers'].items(), key=lambda x: -x[1])) + '.']
    ds = data['deepseek_balance']
    if ds and 'total' in ds:
        lines.append(f"Solde reel du compte DeepSeek : {ds['total']} {ds['currency']}" + ('' if ds.get('available') else ' (compte indisponible)') + '.')
    elif ds:
        lines.append(f"Solde DeepSeek indisponible pour le moment ({ds['error']}).")
    lines.append("Solde des credits prepayes Gemini : pas d'API publique, a verifier dans Google AI Studio (Billing).")
    lines.append('Les plafonds LiteLLM limitent les depenses mais ne paient pas les fournisseurs : les soldes DeepSeek et Gemini doivent les couvrir.')
    return '\n'.join(lines) + '\n'


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        print('%s %s' % (self.command, fmt % args), flush=True)

    def do_GET(self):
        if self.path not in ('/', '/json', '/health'):
            self.send_error(404)
            return
        if self.path == '/health':
            body, kind = b'{"ok":true}', 'application/json'
        else:
            try:
                if not CACHE['data'] or time.time() - CACHE['at'] > 60:
                    CACHE.update(data=collect(), at=time.time())
            except OSError as exc:
                self.send_error(502, 'Sources indisponibles: ' + type(exc).__name__)
                return
            if self.path == '/json':
                body, kind = json.dumps(CACHE['data'], ensure_ascii=False).encode(), 'application/json'
            else:
                body, kind = text(CACHE['data']).encode(), 'text/plain; charset=utf-8'
        self.send_response(200)
        self.send_header('Content-Type', kind)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', 8080), Handler).serve_forever()
