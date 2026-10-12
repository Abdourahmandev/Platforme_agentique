"""Prove a member cap applies across keys; separate fixture, no production reset."""
import json
import uuid
import requests
from common import STATE, api, docker


def main():
    suffix=uuid.uuid4().hex
    team='training-budget-'+suffix
    user='training-fixture-'+suffix
    keys=[]
    checks={}
    try:
        api('/user/new',{'user_id':user,'user_role':'internal_user','auto_create_key':False})
        api('/team/new',{'team_id':team,'max_budget':1,'models':['asia-rapide']})
        api('/team/member_add',{'team_id':team,'max_budget_in_team':0.000001,'member':{'role':'user','user_id':user}})
        for _ in range(2):
            keys.append(api('/key/generate',{'user_id':user,'team_id':team,'models':['asia-rapide'],
                'key_type':'llm_api','duration':'5m','max_budget':1})['key'])
        query='UPDATE "LiteLLM_TeamMembership" SET spend=1 WHERE team_id=\''+team+'\' AND user_id=\''+user+'\';'
        docker('exec','-i','asia-platform-staging-postgres-1','psql','-U','postgres','-d','litellm','-v','ON_ERROR_STOP=1',data=query.encode())
        for i,key in enumerate(keys):
            r=requests.post('http://127.0.0.1:14000/v1/chat/completions',headers={'Authorization':'Bearer '+key},
                json={'model':'asia-rapide','messages':[{'role':'user','content':'Budget fixture: must be blocked'}],'max_tokens':1},timeout=30)
            checks['member_blocks_key_'+str(i)]=r.status_code==422 and r.json().get('error',{}).get('type')=='budget_exceeded'
        print(json.dumps(checks))
        (STATE/'budget-preflight.json').write_text(json.dumps(checks))
        if not all(checks.values()):raise RuntimeError('Shared member cap not enforced')
    finally:
        if keys:api('/key/delete',{'keys':keys})
        api('/team/delete',{'team_ids':[team]})
        api('/user/delete',{'user_ids':[user]})


if __name__=='__main__':main()
