"""Deploy the ticket tool with an exact private rollback snapshot."""
import json
from pathlib import Path
import sys
import control as c

sys.path.insert(0,str(c.ROOT/'infra/training'))
import common as g


def install():
    journal=c.PRIVATE/'openclaw-before.json'
    if journal.exists():
        raise RuntimeError('Rollback snapshot exists; inspect before applying again')
    config=g.remote_json(g.BASE+'/openclaw.json')
    originals={}
    for name in ('asia','developpement','recherche'):
        filename=f'{g.BASE}/workspaces/{name}/AGENTS.md'
        originals[name]=g.node('process.stdout.write(require("fs").readFileSync(JSON.parse(require("fs").readFileSync(0))))',filename).decode()
    c.save('openclaw-before.json',{'config':config,'instructions':originals})
    for source in (c.ROOT/'infra/paperclip/plugin').iterdir():
        if source.is_file():g.remote_write(g.BASE+'/extensions/asia-paperclip/'+source.name,source.read_text(encoding='utf-8'))
    state=c.read('deployment.json')
    catalogue=json.loads((c.ROOT/'infra/agents/catalogue.json').read_text(encoding='utf-8'))
    keys={name:{'id':value['id'],'name':catalogue[name]['name'],'token':c.read('key-'+name+'.json')['token']} for name,value in state['agents'].items()}
    credentials={'enabled':True,'apiUrl':'http://paperclip:3100','publicUrl':state['public_url'].rstrip('/')+'/'+c.read('company.json')['issuePrefix'],
                 'companyId':c.read('company.json')['id'],'projectId':c.read('project.json')['id'],
                 'ownerId':c.read('owner.json')['userId'],'agents':keys}
    g.remote_write(g.BASE+'/paperclip-control/credentials.json',json.dumps(credentials))
    config['plugins']['allow'].append('asia-paperclip')
    config['plugins']['entries']['asia-paperclip']={'enabled':True}
    config['tools']['allow'].append('asia_ticket')
    instructions=(c.ROOT/'infra/paperclip/agent-instructions.md').read_text(encoding='utf-8')
    for name in originals:
        config['agents']['entries'][name]['tools']['allow'].append('asia_ticket')
        g.remote_write(f'{g.BASE}/workspaces/{name}/AGENTS.md',originals[name].rstrip()+'\n\n'+instructions)
    g.remote_write(g.BASE+'/openclaw.json',json.dumps(config,ensure_ascii=False,indent=2))
    try:
        g.docker('exec',g.GATEWAY,'node','dist/index.js','config','validate','--json')
    except Exception:
        restore()
        raise
    print('Plugin files deployed and OpenClaw configuration validated.')


def restore():
    saved=c.read('openclaw-before.json')
    g.remote_write(g.BASE+'/openclaw.json',json.dumps(saved['config'],ensure_ascii=False,indent=2))
    for name,text in saved['instructions'].items():
        g.remote_write(f'{g.BASE}/workspaces/{name}/AGENTS.md',text)
    print('Original configuration and instructions restored. Ticket data retained.')


if __name__=='__main__':
    if '--restore' in sys.argv:restore()
    else:install()
