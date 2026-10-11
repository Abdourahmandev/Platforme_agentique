"""Configure the optional local STT service for each staged OpenClaw agent.

The `openai` adapter/profile is used solely for the OpenAI-compatible Speaches
protocol. Its credential is local, and cannot authenticate to OpenAI's cloud.
"""
import json
import os
from pathlib import Path
import subprocess
import requests

RUNTIME = Path(os.environ['LOCALAPPDATA'])/'AsiaDocker'
DOCKER = r'C:\Program Files\Docker\Docker\resources\bin\docker.exe'
CLI = [DOCKER,'exec','-i','asia-platform-staging-openclaw-1','node','dist/index.js']


def command(args, data=None):
    result = subprocess.run(CLI+args,input=data,capture_output=True,timeout=90)
    if result.returncode:
        (RUNTIME/'audio-configuration-error.log').write_bytes(result.stdout+result.stderr)
        raise RuntimeError('Audio configuration failed. Diagnostic saved in the private runtime.')
    return result.stdout


def main():
    state=json.loads((RUNTIME/'runtime-private.json').read_text())
    if state.get('phase')!='staging':
        raise SystemExit('This initializer is restricted to staging')
    headers={'Authorization':'Bearer '+state['speech_key']}
    response=requests.get('http://127.0.0.1:18000/health',headers=headers,timeout=10)
    if not response.ok:
        raise RuntimeError('The local speech service is unavailable')
    response=requests.post('http://127.0.0.1:18000/v1/models/Systran/faster-whisper-base',headers=headers,timeout=180)
    if not response.ok:
        raise RuntimeError('Speech model installation failed')
    # Refuse to replace an unrelated OpenAI provider that may have been added.
    current=command(['config','get','models.providers','--json'])
    providers=json.loads(current)
    existing=providers.get('openai',{})
    if existing and existing.get('baseUrl')!='http://speaches:8000/v1':
        raise RuntimeError('An unrelated OpenAI provider exists; keep its configuration and use a separate audio profile design.')
    for agent in ('asia','developpement','recherche'):
        command(['models','auth','paste-api-key','--agent',agent,'--provider','openai',
                 '--profile-id','openai:audio'],(state['speech_key']+'\n').encode())
    provider={'api':'openai-completions','baseUrl':'http://speaches:8000/v1','auth':'api-key',
              'request':{'allowPrivateNetwork':True},'models':[]}
    command(['config','set','models.providers.openai',json.dumps(provider),'--strict-json'])
    media={'models':[{'provider':'openai','model':'Systran/faster-whisper-base','profile':'openai:audio',
                     'baseUrl':'http://speaches:8000/v1','capabilities':['audio'],'timeoutSeconds':90}],
           'audio':{'enabled':True,'maxBytes':20971520}}
    command(['config','set','tools.media',json.dumps(media),'--strict-json'])
    print('Local transcription configured for three agents. No cloud speech key is used.')


if __name__=='__main__':
    main()
