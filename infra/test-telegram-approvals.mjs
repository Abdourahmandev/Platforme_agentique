// Operator-assisted Telegram test. This program never resolves an approval.
// Only harmless, distinct echo commands are submitted, one per test case.
import fs from 'node:fs';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {execFileSync,spawn} from 'node:child_process';
import {approvalChecks} from './telegram-approval-evidence.mjs';

const root=path.join(process.env.LOCALAPPDATA,'AsiaDocker');
const attempt=process.env.ASIA_TELEGRAM_APPROVAL_TEST||'';
if(attempt&&!/^[a-z0-9-]{1,40}$/.test(attempt))throw Error('Invalid test attempt name');
const file=path.join(root,'telegram-approval-test'+(attempt?'-'+attempt:'')+'-private.json');
const state=JSON.parse(fs.readFileSync(path.join(root,'runtime-private.json'),'utf8'));
const docker=(process.platform === 'win32' ? 'C:\\Program Files\\Docker\\Docker\\resources\\bin\\docker.exe' : 'docker');
const container='asia-platform-staging-openclaw-1';
const [action,choice]=process.argv.slice(2);
if(!['prepare','present','observe','verify','cancel'].includes(action)||!['deny','allow'].includes(choice))throw Error('Use prepare|present|observe|verify|cancel deny|allow');
const journal=fs.existsSync(file)?JSON.parse(fs.readFileSync(file,'utf8')):{id:randomUUID(),createdAt:new Date().toISOString(),cases:{}};
const save=()=>{fs.writeFileSync(file+'.tmp',JSON.stringify(journal,null,2));fs.renameSync(file+'.tmp',file);};
const delay=ms=>new Promise(r=>setTimeout(r,ms));
const sessionKey='agent:asia:telegram-approval-test-'+journal.id+'-'+choice;
async function invoke(args){
  const r=await fetch('http://127.0.0.1:18789/tools/invoke',{method:'POST',
    headers:{Authorization:'Bearer '+state.gateway_token,'Content-Type':'application/json'},
    body:JSON.stringify({tool:'asia_opencode_task',agentId:'asia',sessionKey,args}),signal:AbortSignal.timeout(45000)});
  const b=await r.json();if(!r.ok||b.result?.isError)throw Error('Bridge rejected operation; inspect private evidence');
  return b.result.details;
}
function trace(taskId){
  // Read only the synthetic session owned by this test; no other chat content.
  const code=`import fs from 'node:fs';const {Bridge}=await import('/home/node/.openclaw/extensions/asia-opencode/bridge.mjs');const b=new Bridge({stateFile:'/home/node/.openclaw/asia-opencode/tasks.json',credentials:()=>JSON.parse(fs.readFileSync('/home/node/.openclaw/credentials/asia-opencode.json','utf8'))});const task=b.own(process.argv[1]);const messages=await b.request('/session/'+task.sessionId+'/message');console.log(JSON.stringify(messages));`;
  return JSON.parse(execFileSync(docker,['exec',container,'node','--input-type=module','-e',code,taskId],{encoding:'utf8',windowsHide:true,timeout:35000,maxBuffer:2*1024*1024}));
}
function inspectTrace(entry){
  const messages=trace(entry.taskId);
  fs.writeFileSync(path.join(root,'telegram-approval-'+journal.id+'-'+choice+'-trace.json'),JSON.stringify(messages));
  const calls=messages.flatMap(m=>(m.parts||[]).filter(p=>p.type==='tool'));
  const bash=calls.filter(p=>p.tool==='bash');
  if(calls.some(p=>p.tool!=='bash')||bash.some(p=>p.state?.input?.command!==entry.command))throw Error('Unexpected fixture tool/command; inspect private trace');
  return {calls:bash.length,completed:bash.filter(p=>p.state?.status==='completed').length,
    failed:bash.filter(p=>p.state?.status==='error').length,
    outputMatches:bash.some(p=>p.state?.status==='completed'&&p.state?.output?.trim()===entry.marker)};
}
function nativeApprovals(entry){
  const code=`import {DatabaseSync} from 'node:sqlite';const db=new DatabaseSync('/home/node/.openclaw/state/openclaw.sqlite',{readOnly:true});try{console.log(JSON.stringify(db.prepare('SELECT approval_id,status,presentation_json,decision,terminal_reason,resolver_kind,resolver_id,source_run_id FROM operator_approvals WHERE source_session_key=?').all(process.argv[1])));}finally{db.close();}`;
  const rows=JSON.parse(execFileSync(docker,['exec',container,'node','--input-type=module','-e',code,entry.sessionKey],{encoding:'utf8',windowsHide:true,timeout:15000,stdio:['ignore','pipe','pipe']}));
  return rows.filter(row=>JSON.parse(row.presentation_json).description==='bash: '+JSON.stringify([entry.command]));
}
async function main(){
  let entry=journal.cases[choice];
  if(action==='prepare'){
    if(entry)throw Error('Case already journaled; inspect it instead of resubmitting');
    if(choice==='allow'&&journal.cases.deny?.phase!=='verified')throw Error('Verify a real native denial before preparing the separate allowed case');
    const marker='ASIA_TELEGRAM_'+choice.toUpperCase()+'_'+randomUUID().replaceAll('-','').slice(0,10);
    entry=journal.cases[choice]={marker,command:'echo '+marker,requestId:randomUUID(),phase:'submission-uncertain',sessionKey};save();
    const started=await invoke({action:'start',requestId:entry.requestId,prompt:`Test technique autorise par le proprietaire. Execute une seule fois exactement la commande bash ${entry.command}. Attends la permission native. Si elle est refusee, termine sans reessayer. Ne lis ni ne modifie aucun fichier, ne lance aucun autre outil ou commande. Donne uniquement la sortie reelle ou le refus.`});
    entry.taskId=started.taskId;entry.submission=started.submission;save();
    const deadline=Date.now()+150000;
    while(Date.now()<deadline){
      const s=await invoke({action:'status',taskId:entry.taskId});
      const permission=s.permissions.find(p=>p.permission==='bash'&&JSON.stringify(p.patterns)===JSON.stringify([entry.command]));
      if(permission){entry.permissionId=permission.id;entry.phase='ready';entry.before=inspectTrace(entry);save();console.log(JSON.stringify({case:choice,phase:entry.phase,command:entry.command,noExecution:entry.before.completed===0}));return;}
      if(s.completed||s.error)throw Error('Synthetic task ended without requesting expected permission');
      await delay(1500);
    }
    throw Error('Permission did not appear; do not resubmit');
  }
  if(!entry?.taskId)throw Error('Prepare the case first');
  if(action==='observe'){
    const rows=nativeApprovals(entry);console.log(JSON.stringify({case:choice,phase:entry.phase,native:rows.map(r=>({status:r.status,decision:r.decision,reason:r.terminal_reason,resolver:r.resolver_kind}))}));return;
  }
  if(action==='cancel'){
    entry.cleanup=await invoke({action:'cancel',taskId:entry.taskId});save();console.log(JSON.stringify({case:choice,cancelled:true}));return;
  }
  if(action==='verify'){
    const status=await invoke({action:'status',taskId:entry.taskId});
    const evidence=inspectTrace(entry);
    // Read durable native records, independently of observer/device capabilities.
    // An automatic timeout also has decision=deny: require a human channel verdict.
    entry.nativeEvidence=nativeApprovals(entry);
    const checks=approvalChecks(choice,evidence,status,entry.nativeEvidence);
    // Preserve the expected case, even when the owner clicked another button.
    // Record the actual observed outcome separately; never relabel a denial pass.
    entry.observedChecks=Object.fromEntries(['deny','allow'].map(decision=>[
      decision,approvalChecks(decision,evidence,status,entry.nativeEvidence)]));
    entry.verification={evidence,status,at:new Date().toISOString()};entry.checks=checks;
    entry.phase=Object.values(checks).every(Boolean)?'verified':'needs-review';save();
    console.log(JSON.stringify({case:choice,checks,observedChecks:entry.observedChecks}));if(entry.phase!=='verified')process.exitCode=1;return;
  }
  if(entry.phase!=='ready')throw Error('Presentation already dispatched or uncertain; no automatic retry');
  entry.before=inspectTrace(entry);save();
  if(entry.before.completed!==0)throw Error('Fixture already executed; inspect evidence');
  const config=JSON.parse(execFileSync(docker,['exec',container,'node','-e',`const fs=require('fs'),c=JSON.parse(fs.readFileSync('/home/node/.openclaw/openclaw.json'));console.log(JSON.stringify(c.channels.telegram.accounts.asia));`],{encoding:'utf8',windowsHide:true,timeout:15000}));
  const owners=config.allowFrom?.filter(v=>/^\d+$/.test(String(v)));
  if(owners?.length!==1||config.allowFrom.length!==1||!config.execApprovals?.enabled||config.execApprovals.target!=='dm'||
    JSON.stringify(config.execApprovals.approvers?.map(String))!==JSON.stringify(owners.map(String))||
    JSON.stringify(config.execApprovals.agentFilter)!==JSON.stringify(['asia']))throw Error('Expected native private approvals for Asia and her single owner');
  const log=fs.openSync(path.join(root,'telegram-approval-'+journal.id+'-'+choice+'-cli.log'),'w');
  try{
    entry.phase='presentation-dispatched';save();
    const message=`Test Telegram distinct ${choice}. Une tache Windows artificielle attend la permission pour ${entry.command}. Utilise tool_search puis tool_describe pour asia_opencode_approve et asia_opencode_task. Appelle exactement asia_opencode_approve avec taskId=${entry.taskId} et permissionId=${entry.permissionId}. Le proprietaire repondra aux boutons Telegram. Ne valide jamais toi-meme. Si le proprietaire refuse explicitement, utilise asia_opencode_task action reject avec ces identifiants, ou cancel pour cette tache, puis termine sans reessayer. Si la demande expire ou ne peut pas etre livree, annule uniquement cette tache de test avec cancel ; explique « aucune decision recue, test annule », sans attribuer un refus au proprietaire. Si autorise, consulte status sur cette meme tache et rapporte la sortie reelle. Ne cree aucune tache, ne delegue rien et ne touche aucun fichier. Reponds en francais avec un bref bilan du test.`;
    const child=spawn(docker,['exec',container,'node','dist/index.js','agent','--agent','asia','--session-key',sessionKey,
      '--message',message,'--to',String(owners[0]),'--channel','telegram','--deliver','--reply-channel','telegram','--reply-account','asia','--reply-to',String(owners[0]),'--timeout','240','--json'],{windowsHide:true,stdio:['ignore',log,log],timeout:300000});
    const code=await new Promise((resolve,reject)=>{child.once('error',reject);child.once('exit',resolve);});
    entry.agentExit=code;entry.phase=code===0?'presentation-finished':'presentation-uncertain';save();
    console.log(JSON.stringify({case:choice,agentExit:code}));
    if(code!==0)process.exitCode=1;
  }finally{fs.closeSync(log);}
}
main().catch(error=>{journal.lastError={case:choice,action,message:error.message,at:new Date().toISOString()};save();console.error(error.message);process.exitCode=1;});
