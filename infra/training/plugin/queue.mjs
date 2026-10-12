import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';

export const OPERATIONS = ['node_tests','python_tests','build'];
export function validate(params) {
  if(!['start','status','cancel'].includes(params.action))throw Error('Action interdite');
  if(params.action==='start'&&!OPERATIONS.includes(params.operation))throw Error('Operation interdite');
  if(params.action!=='start'&&!/^[a-f0-9]{32}$/.test(params.jobId||''))throw Error('Identifiant invalide');
}
export class Queue {
  constructor(root){this.root=root;}
  read(name){return JSON.parse(fs.readFileSync(path.join(this.root,name),'utf8'));}
  async call(context,callId,params){
    if(context.agentId!=='formation-developpement'||!context.sessionKey)throw Error('Outil reserve au developpeur en formation');
    validate(params);
    const control=this.read('control.json');
    if(!control.active)throw Error('Formation suspendue');
    if(params.action==='start'){
      const heartbeat=this.read('heartbeat.json');
      if(Date.now()-heartbeat.timestamp>15000)throw Error('Executeur indisponible; aucune tache soumise');
      const jobId=createHash('sha256').update(context.sessionKey+'\0'+callId).digest('hex').slice(0,32);
      const request={jobId,agentId:context.agentId,sessionKey:context.sessionKey,operation:params.operation};
      const filename=path.join(this.root,jobId+'.request.json');
      try{fs.writeFileSync(filename,JSON.stringify(request),{flag:'wx',mode:0o600});}
      catch(e){if(e.code!=='EEXIST')throw e;if(JSON.stringify(this.read(jobId+'.request.json'))!==JSON.stringify(request))throw Error('Requete modifiee');}
      // A bounded wait usually returns the real test result in the same tool call.
      for(let i=0;i<25;i++){
        if(fs.existsSync(path.join(this.root,jobId+'.result.json')))return this.read(jobId+'.result.json');
        await new Promise(r=>setTimeout(r,1000));
      }
      return {jobId,status:'queued_or_running',note:'Consulter status avec ce jobId. Ne pas resoumettre.'};
    }
    const request=this.read(params.jobId+'.request.json');
    if(request.sessionKey!==context.sessionKey||request.agentId!==context.agentId)throw Error('Mission etrangere');
    if(params.action==='cancel'){
      fs.writeFileSync(path.join(this.root,params.jobId+'.cancel'),'',{mode:0o600});
      return {jobId:params.jobId,status:'cancellation_requested'};
    }
    const result=path.join(this.root,params.jobId+'.result.json');
    return fs.existsSync(result)?this.read(params.jobId+'.result.json'):{jobId:params.jobId,status:'queued_or_running'};
  }
}
