"""Real LiteLLM Router, simulated upstreams: no paid provider calls or credentials.

Run inside the pinned LiteLLM image with --network none. Every concrete model is
replaced by a loopback HTTP fixture, retaining the real routing configuration.
"""
import asyncio
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
import yaml
from litellm import Router
from routing_context import guard

seen = []
failed = set()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        seen.append(data['model'])
        bad = data['model'] in failed
        body = {'error': {'message': 'Simulated outage', 'type': 'server_error'}} if bad else {
            'id': 'fixture', 'object': 'chat.completion', 'created': 1, 'model': data['model'],
            'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': 'OK'}, 'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': 1, 'completion_tokens': 1, 'total_tokens': 2},
        }
        self.send_response(503 if bad else 200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())


async def main():
    global failed
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    config = yaml.safe_load(Path(__file__).with_name('config.yaml').read_text(encoding='utf-8'))
    for model in config['model_list']:
        if model['model_name'] != 'asia-auto':
            model['litellm_params'] = {'model': 'openai/' + model['model_name'], 'api_key': 'fixture',
                                     'api_base': f'http://127.0.0.1:{server.server_port}', 'max_retries': 0}
    image = {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,iVBORw0KGgo='}}
    pdf = {'type': 'file', 'file': {'filename': 'fixture.pdf', 'file_data': 'data:application/pdf;base64,' + base64.b64encode(b'%PDF-1.4\n%%EOF').decode()}}
    schema = {'type': 'json_schema', 'json_schema': {'name': 'fixture', 'schema': {'type': 'object'}}}
    cases = [
        ('text', 'gemini-3.1-flash-lite', None, None, ['gemini-3.1-flash-lite', 'asia-rapide']),
        ('auto image', 'asia-auto', image, None, ['asia-rapide', 'gemini-3.1-flash-lite']),
        ('manual image', 'gemini-3.1-flash-lite', image, None, ['gemini-3.1-flash-lite', 'gemini-3.8-flash']),
        ('PDF', 'asia-auto', pdf, None, ['gemini-3.1-flash-lite', 'gemini-3.8-flash']),
        ('strict JSON', 'asia-auto', None, schema, ['gemini-3.1-flash-lite', 'gemini-3.8-flash']),
    ]
    try:
        for name, model, part, fmt, expected in cases:
            seen.clear()
            failed = {expected[0]}
            data = {'model': model, 'messages': [{'role': 'user', 'content': [{'type': 'text', 'text': 'Bonjour'}, *([part] if part else [])]}]}
            if fmt:
                data['response_format'] = fmt
            data = await guard.async_pre_call_hook(None, None, data, None)
            router = Router(model_list=config['model_list'], **config['router_settings'])
            result = await router.acompletion(**data)
            if seen != expected or result.choices[0].message.content != 'OK':
                raise AssertionError((name, seen))
            print(json.dumps({'test': name, 'passed': True, 'route': seen}), flush=True)
        seen.clear()
        failed = set(expected)
        router = Router(model_list=config['model_list'], **config['router_settings'])
        try:
            await router.acompletion(**data)
        except Exception:
            pass
        else:
            raise AssertionError('Expected bounded failure')
        if seen != expected:
            raise AssertionError(('Unexpected retry/fallback', seen))
        print(json.dumps({'test': 'bounded outage', 'passed': True, 'attempts': len(seen)}))
    finally:
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    asyncio.run(main())
