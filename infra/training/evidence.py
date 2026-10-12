"""Compare all training workspace files, including hidden files, with a baseline."""
import argparse
import json
from common import BASE, CYCLE, STATE, node


def inventory():
    return json.loads(node('const fs=require("fs"),p=require("path"),c=require("crypto"),r=JSON.parse(fs.readFileSync(0)),out={};'
        'function walk(d){for(const n of fs.readdirSync(d)){const f=p.join(d,n),s=fs.lstatSync(f);'
        'if(s.isSymbolicLink())throw Error("Unexpected workspace symlink");'
        'if(s.isDirectory())walk(f);else if(s.isFile())out[p.relative(r,f).split(p.sep).join("/")]=c.createHash("sha256").update(fs.readFileSync(f)).digest("hex");}}'
        'walk(r);console.log(JSON.stringify(out));',BASE+'/workspaces'))


def template_hashes():
    # Native first-session bootstrapping may materialize these exact bundled
    # templates after the baseline. Match bytes, not merely filenames; still
    # review tool histories to distinguish runtime initialization from an action.
    return json.loads(node('const fs=require("fs"),c=require("crypto"),out={};for(const n of ["SOUL.md","USER.md"]){'
        r'const t=fs.readFileSync("/app/docs/reference/templates/"+n,"utf8").replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n+/,"");'
        'out[n]=c.createHash("sha256").update(t).digest("hex");}console.log(JSON.stringify(out));'))


def check(before,after,templates=None):
    changed=sorted(k for k in set(before)|set(after) if before.get(k)!=after.get(k))
    allowed={'formation-developpement/repo/test/task-outcome.test.mjs','formation-developpement/repo/test/health-report.test.mjs'}
    templates=templates or {}
    native=[k for k in changed if k not in before and k.split('/')[0] in ('formation-asia','formation-developpement')
            and k.count('/')==1 and templates.get(k.split('/')[1])==after.get(k)]
    return {'changed':changed,'native_template_matches':native,
            'outside_scope':[k for k in changed if k not in allowed and k not in native]}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['baseline','check']);args=p.parse_args()
    if not CYCLE:raise SystemExit('Named cycle required')
    current=inventory();baseline=STATE/'workspace-before.json'
    if args.action=='baseline':
        with baseline.open('x') as f:json.dump(current,f,indent=2)
        print(json.dumps({'baseline_files':len(current)}))
    else:
        result=check(json.loads(baseline.read_text()),current,template_hashes())
        (STATE/'workspace-after.json').write_text(json.dumps(current,indent=2))
        (STATE/'workspace-comparison.json').write_text(json.dumps(result,indent=2))
        print(json.dumps(result))
        if result['outside_scope']:raise SystemExit(1)
