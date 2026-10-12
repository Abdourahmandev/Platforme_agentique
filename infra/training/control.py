"""Operator checks and reviewed coaching; no credentials in public output."""
import argparse
import json
from common import BASE, CONTROL, IDS, ROOT, STATE, TEAM, api, balances, remote_json, remote_write
from configure import instructions


def check():
    j=json.loads((STATE/'journal.json').read_text())
    b=balances()
    credit=next(float(v['total_balance']) for v in b['deepseek'] if v['currency']=='USD')
    spend={a:float(api('/key/info',params={'key':key})['info'].get('spend') or 0) for a,key in j['keys'].items()}
    team=api('/team/info',params={'team_id':TEAM})['team_info']
    allowed=(j['status']=='active' and credit>0.25 and sum(spend.values())<min(4.0,j['budget_usd']*0.85)
             and float(team.get('spend') or 0)<float(team['max_budget'])
             and b['tavily']['plan_usage']<b['tavily']['plan_limit'] and not b['tavily']['paygo_usage'])
    return {'continue':allowed,'deepseek_usd':credit,'spend_by_agent':spend,'training_spend_usd':sum(spend.values()),
        'budget_usd':j['budget_usd'],'tavily':b['tavily']}


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('action',choices=['check','coach'])
    args=p.parse_args()
    try:
        if args.action=='check': print(json.dumps(check()))
        else:
            for agent in IDS:
                role=agent.removeprefix('formation-')
                remote_write(BASE+'/workspaces/'+agent+'/PLAYBOOK.md',(ROOT/'infra/training/playbooks'/f'{role}.md').read_text(encoding='utf-8'))
                remote_write(BASE+'/workspaces/'+agent+'/AGENTS.md',instructions(role,improved=True))
            print('Reviewed coaching installed for training identities only')
    except Exception as e:
        print(json.dumps({'continue':False,'error_type':type(e).__name__}))
        raise SystemExit(1)
