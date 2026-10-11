"""Prepare a credential dedicated to the private local transcription service."""
import json
import os
from pathlib import Path
import secrets

root=Path(os.environ['LOCALAPPDATA'])/'AsiaDocker'
p=root/'runtime-private.json'
state=json.loads(p.read_text())
if state.get('phase')!='staging':
    raise SystemExit('This initializer is restricted to staging')
key=state.setdefault('speech_key','sk-local-'+secrets.token_hex(32))
if not key.startswith('sk-local-'):
    key='sk-local-'+key
    state['speech_key']=key
p.write_text(json.dumps(state),encoding='utf-8')
(root/'speaches.env').write_text("API_KEY='"+key+"'\n",encoding='utf-8')
print('Prepared the dedicated local transcription credential.')
