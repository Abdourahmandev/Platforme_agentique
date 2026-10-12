// One supervised mission at a time. Never retries an uncertain chat.send.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
import {randomUUID} from 'node:crypto';
import {GatewayClient,loadDevice} from '../gateway-client.mjs';
const dir=path.dirname(fileURLToPath(import.meta.url));
const root=path.join(process.env.LOCALAPPDATA,'AsiaDocker');
const cycle=process.env.ASIA_TRAINING_CYCLE||'';
if(cycle&&!/^cycle-[1-9][0-9]{0,3}$/.test(cycle))throw Error('Invalid training cycle');
const out=cycle?path.join(root,'training','cycles',cycle):path.join(root,'training');
const missionId=process.argv[2];
const curriculum=JSON.parse(fs.readFileSync(path.join(dir,cycle?'curriculum-followup.json':'curriculum.json'),'utf8'));
const mission=curriculum.find(m=>m.id===missionId);
if(!mission)throw Error('Unknown mission');
const receiptFile=path.join(out,missionId+'.json');
if(fs.existsSync(receiptFile))throw Error('Existing receipt; inspect outcome before any correction mission');
const budget=spawnSync('python',[path.join(dir,'control.py'),'check'],{encoding:'utf8',windowsHide:true});
if(budget.status!==0)throw Error('Budget check unavailable');
const before=JSON.parse(budget.stdout);
if(!before.continue)throw Error('Training budget or credit gate closed');
const s=JSON.parse(fs.readFileSync(cycle?path.join(out,'connection.json'):path.join(root,'runtime-private.json'),'utf8'));
const client=new GatewayClient({url:cycle?s.url:'ws://127.0.0.1:18789',token:s.gateway_token,device:loadDevice(path.join(cycle?out:root,'gateway-test-device.json'))});
const parent=mission.continuationOf?JSON.parse(fs.readFileSync(path.join(out,mission.continuationOf+'.json'),'utf8')):null;
const agent='formation-'+mission.agent;
if(parent&&(parent.status!=='completed'||parent.agent!==agent))throw Error('Clarification requires a completed same-agent turn');
const sessionKey=parent?.sessionKey||'agent:'+agent+':'+missionId+'-'+randomUUID();
const marker='FORMATION_FIN_'+missionId;
const receipt={id:missionId,agent,sessionKey,started_at:new Date().toISOString(),budget_before:before,status:'submitting'};
receipt.prompt=mission.prompt;receipt.continuationOf=mission.continuationOf;
fs.writeFileSync(receiptFile,JSON.stringify(receipt,null,2));
let completed=false;
function assistantText(h){return (h.messages||[]).filter(m=>m.role==='assistant').map(m=>typeof m.content==='string'?m.content:m.content?.filter(x=>x.type==='text').map(x=>x.text).join('\n')).filter(Boolean);}
function walk(v,visit){if(!v||typeof v!=='object')return;visit(v);for(const x of Object.values(v)){
  if(typeof x==='string'&&/^[\[{]/.test(x.trim())){try{walk(JSON.parse(x),visit);}catch{}}
  else walk(x,visit);
}}
const children=new Set();
try{
  await client.connect();
  const events=[];client.onEvent(e=>{if(e.event==='chat'&&e.payload.sessionKey===sessionKey)events.push(e.payload);});
  const ack=await client.request('chat.send',{sessionKey,idempotencyKey:randomUUID(),message:mission.prompt+'\nReponds en francais. Termine ta reponse finale par '+marker+'.'});
  receipt.runId=ack.runId;receipt.status='running';fs.writeFileSync(receiptFile,JSON.stringify(receipt,null,2));
  const deadline=Date.now()+360000;
  while(Date.now()<deadline){
    const h=await client.request('chat.history',{sessionKey,limit:160});
    fs.writeFileSync(path.join(out,missionId+'-history.json'),JSON.stringify(h));
    walk(h,v=>{if(typeof v.childSessionKey==='string')children.add(v.childSessionKey);});
    const text=assistantText(h).at(-1)||'';
    if(text.includes(marker)){
      receipt.response=text.replace(marker,'').trim();receipt.status='completed';completed=true;break;
    }
    const last=(h.messages||[]).at(-1);
    if(last?.role==='assistant'&&['length','error','aborted'].includes(last.stopReason))throw Error('Terminal agent output: '+last.stopReason);
    if(events.some(e=>['error','aborted'].includes(e.state)))throw Error('Agent run failed or aborted');
    await new Promise(r=>setTimeout(r,3000));
  }
  if(!completed)throw Error('Mission deadline; outcome must be inspected');
  for(const key of children){
    const h=await client.request('chat.history',{sessionKey:key,limit:120});
    fs.writeFileSync(path.join(out,missionId+'-child-'+key.split(':')[1]+'.json'),JSON.stringify(h));
  }
}catch(e){receipt.status='incomplete';receipt.error=e.message;process.exitCode=1;}
finally{
  if(!completed){for(const key of [sessionKey,...children]){try{await client.request('chat.abort',{sessionKey:key});}catch{}}}
  client.close();receipt.children=[...children];receipt.finished_at=new Date().toISOString();
  const after=spawnSync('python',[path.join(dir,'control.py'),'check'],{encoding:'utf8',windowsHide:true});
  if(after.status===0){try{receipt.budget_after=JSON.parse(after.stdout);}catch{}}
  fs.writeFileSync(receiptFile,JSON.stringify(receipt,null,2));
  console.log(JSON.stringify({id:missionId,status:receipt.status,response:receipt.response,error:receipt.error,children:receipt.children,
    training_spend_usd:receipt.budget_after?.training_spend_usd}));
}
