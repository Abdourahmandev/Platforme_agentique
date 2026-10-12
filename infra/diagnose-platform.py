"""Read-only observations for the health report. No credentials or model requests."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess

SERVICES=('postgres','litellm','openclaw','speaches','playwright')
DOCKER=r'C:\Program Files\Docker\Docker\resources\bin\docker.exe' if os.name=='nt' else 'docker'


def backup_observation(report,now):
    archive=Path(report.get('archive',''))
    if not archive.is_file():return {'verified':None,'ageHours':None}
    flags=[report.get(k) for k in ['openclaw_native_verify','openclaw_restored','postgres_restored']]
    verified=False if any(v is False for v in flags) else True if all(v is True for v in flags) else None
    return {'verified':verified,'ageHours':round((now-archive.stat().st_mtime)/3600,3)}


def collect():
    out={'observedAt':datetime.now(timezone.utc).isoformat(),'services':[],'backup':{'verified':None,'ageHours':None},
         'delegation':{'state':'unknown'},'limitations':['Ce relevé ne teste ni Telegram ni une délégation réelle.']}
    for service in SERVICES:
        try:
            p=subprocess.run([DOCKER,'inspect','--format','{{json .State}}','asia-platform-staging-'+service+'-1'],
                capture_output=True,text=True,timeout=8)
            state=json.loads(p.stdout) if p.returncode==0 else {}
            running=state.get('Running')
            health=state.get('Health',{}).get('Status')
            value=False if running is False or health=='unhealthy' else True if running is True and health=='healthy' else None
        except (OSError,ValueError,subprocess.TimeoutExpired):value=None
        out['services'].append({'name':service,'healthy':value})
    try:
        report=json.loads((Path(os.environ.get('LOCALAPPDATA','/tmp'))/'AsiaDocker/docker-backup-result.json').read_text())
        out['backup']=backup_observation(report,datetime.now(timezone.utc).timestamp())
    except (OSError,ValueError):pass
    return out


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--json',action='store_true',help='Explicit machine-readable output (also the default)')
    parser.parse_args()
    print(json.dumps(collect(),ensure_ascii=False,indent=2))
