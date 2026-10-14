"""OpenAI-compatible /v1/audio/speech proxy that transcodes Gemini WAV for OpenClaw.

Gemini TTS (through LiteLLM) only returns WAV/PCM. Telegram voice notes need
OGG/Opus, and the official OpenClaw image ships without ffmpeg. This proxy asks
LiteLLM for WAV and converts it to the requested format. The caller's bearer key
is forwarded unchanged, so LiteLLM budgets and key restrictions still apply.
Standard library only; no credential is stored or logged here.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import subprocess
import urllib.error
import urllib.request

UPSTREAM = os.environ.get('UPSTREAM', 'http://litellm:4000')
MAX_BODY = 64 * 1024
# requested format -> (ffmpeg arguments, content type)
FORMATS = {
    'opus': (['-c:a', 'libopus', '-b:a', '48k', '-application', 'voip', '-f', 'ogg'], 'audio/ogg'),
    'mp3': (['-c:a', 'libmp3lame', '-b:a', '64k', '-f', 'mp3'], 'audio/mpeg'),
    'aac': (['-c:a', 'aac', '-b:a', '64k', '-f', 'adts'], 'audio/aac'),
    'flac': (['-c:a', 'flac', '-f', 'flac'], 'audio/flac'),
}


class Handler(BaseHTTPRequestHandler):
    server_version = 'asia-tts-proxy'

    def log_message(self, fmt, *args):  # status line only, never bodies or headers
        print('%s %s' % (self.command, fmt % args), flush=True)

    def reply(self, code, body, content_type='application/json'):
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def error(self, code, message):
        self.reply(code, json.dumps({'error': {'message': message}}).encode())

    def do_GET(self):
        if self.path == '/health':
            return self.reply(200, b'{"ok":true}')
        self.error(404, 'not found')

    def do_POST(self):
        if self.path not in ('/v1/audio/speech', '/audio/speech'):
            return self.error(404, 'not found')
        length = int(self.headers.get('Content-Length') or 0)
        if not 0 < length <= MAX_BODY:
            return self.error(413, 'invalid body size')
        try:
            request = json.loads(self.rfile.read(length))
        except ValueError:
            return self.error(400, 'invalid JSON')
        wanted = request.get('response_format') or 'mp3'
        if wanted not in FORMATS and wanted not in ('wav', 'pcm'):
            return self.error(400, 'unsupported response_format: ' + str(wanted))
        upstream = dict(request, response_format='pcm' if wanted == 'pcm' else 'wav')
        call = urllib.request.Request(UPSTREAM + '/v1/audio/speech', data=json.dumps(upstream).encode(),
                                      headers={'Content-Type': 'application/json',
                                               'Authorization': self.headers.get('Authorization', '')})
        try:
            with urllib.request.urlopen(call, timeout=120) as response:
                audio = response.read()
        except urllib.error.HTTPError as exc:  # pass LiteLLM errors (budget, auth) through
            return self.reply(exc.code, exc.read(), exc.headers.get('Content-Type', 'application/json'))
        except (urllib.error.URLError, TimeoutError):
            return self.error(502, 'speech gateway unavailable')
        if wanted in ('wav', 'pcm'):
            return self.reply(200, audio, 'audio/wav' if wanted == 'wav' else 'audio/pcm')
        args, content_type = FORMATS[wanted]
        result = subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-i', 'pipe:0', '-ac', '1',
                                 *args, 'pipe:1'], input=audio, capture_output=True, timeout=60)
        if result.returncode or not result.stdout:
            return self.error(502, 'audio conversion failed')
        self.reply(200, result.stdout, content_type)


if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', 8080), Handler).serve_forever()
