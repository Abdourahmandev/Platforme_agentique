"""Generate a synthetic French MP3 and transcribe it locally to check the content."""
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
import requests

RUNTIME=Path(os.environ['LOCALAPPDATA'])/'AsiaDocker'
DOCKER=r'C:\Program Files\Docker\Docker\resources\bin\docker.exe'
EXEC=[DOCKER,'exec','-i','asia-platform-staging-openclaw-1']


def main():
    filename='/tmp/asia-tts-test-'+uuid.uuid4().hex+'.mp3'
    def run(args):
        return subprocess.run(EXEC+args,capture_output=True,timeout=150)
    checks={}
    try:
        p=run(['node','dist/index.js','infer','tts','convert','--provider','microsoft',
               '--text','Bonjour, ceci est un test audio.','--output',filename,'--gateway','--json'])
        try: result=json.loads(p.stdout)
        except ValueError: result={}
        checks['generation']={'passed':p.returncode==0 and result.get('ok') is True}
        p=run(['node','-e','process.stdout.write(require("fs").readFileSync(process.argv[1]))',filename])
        checks['nonempty_mp3']={'passed':p.returncode==0 and len(p.stdout)>1000}
        state=json.loads((RUNTIME/'runtime-private.json').read_text())
        r=requests.post('http://127.0.0.1:18000/v1/audio/transcriptions',
            headers={'Authorization':'Bearer '+state['speech_key']},
            files={'file':('fixture.mp3',p.stdout,'audio/mpeg')},
            data={'model':'Systran/faster-whisper-base','language':'fr'},timeout=120)
        text=r.json().get('text','').lower() if r.ok else ''
        checks['spoken_content']={'passed':'bonjour' in text and 'test audio' in text}
    except Exception as exc:
        checks['suite_completed']={'passed':False,'error_type':type(exc).__name__}
    finally:
        p=run(['node','-e','require("fs").rmSync(process.argv[1],{force:true})',filename])
        checks['fixture_cleanup']={'passed':p.returncode==0}
    (RUNTIME/'tts-test-result.json').write_text(json.dumps(checks,indent=2))
    print(json.dumps(checks))
    return 0 if all(c['passed'] for c in checks.values()) else 1


if __name__=='__main__': sys.exit(main())
