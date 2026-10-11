"""Test actual OpenClaw -> Speaches transcription using a synthetic fixture."""
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

ROOT=Path(__file__).resolve().parents[1]
RUNTIME=Path(os.environ['LOCALAPPDATA'])/'AsiaDocker'
DOCKER=r'C:\Program Files\Docker\Docker\resources\bin\docker.exe'
CONTAINER='asia-platform-staging-openclaw-1'


def main():
    remote='/tmp/asia-audio-test-'+uuid.uuid4().hex+'.wav'
    checks={}
    def run(args,data=None):
        return subprocess.run([DOCKER,'exec','-i',CONTAINER,*args],input=data,capture_output=True,timeout=150)
    p=run(['node','-e','require("fs").writeFileSync(process.argv[1],require("fs").readFileSync(0),{flag:"wx",mode:0o600})',remote],
          (ROOT/'test/fixtures/audio-test.wav').read_bytes())
    if p.returncode: raise RuntimeError('Cannot install audio test fixture')
    try:
        for agent in ('asia','developpement','recherche'):
            p=run(['node','dist/index.js','infer','audio','transcribe','--agent',agent,'--file',remote,'--json'])
            try: result=json.loads(p.stdout)
            except ValueError: result={}
            texts=' '.join(item.get('text','') for item in result.get('outputs',[])).lower()
            checks[agent]={'passed':p.returncode==0 and 'audio test' in texts,
                           'local_model':result.get('model')=='Systran/faster-whisper-base'}
            print(json.dumps({agent:checks[agent]}),flush=True)
    finally:
        cleanup=run(['node','-e','require("fs").unlinkSync(process.argv[1])',remote])
        if cleanup.returncode: raise RuntimeError('Audio fixture cleanup failed')
    (RUNTIME/'audio-test-result.json').write_text(json.dumps(checks,indent=2))
    return 0 if all(v['passed'] and v['local_model'] for v in checks.values()) else 1


if __name__=='__main__':
    sys.exit(main())
