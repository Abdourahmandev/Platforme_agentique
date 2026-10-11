// Real native tasks in synthetic WebChat sessions; never sends Telegram messages.
import fs from 'node:fs';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {GatewayClient,loadDevice} from './gateway-client.mjs';

const root=path.join(process.env.LOCALAPPDATA,'AsiaDocker');
const state=JSON.parse(fs.readFileSync(path.join(root,'runtime-private.json'),'utf8'));
const client=new GatewayClient({url:'ws://127.0.0.1:18789',token:state.gateway_token,
  device:loadDevice(path.join(root,'gateway-test-device.json'))});
const suffix=randomUUID();
const sessionKey='agent:asia:delegation-check-'+suffix;
const privateMarker='UNSHARED_'+randomUUID();
const research='RECHERCHE_'+suffix,development='DEVELOPPEMENT_'+suffix;
const checks={};const children=new Set();
const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
function check(name,value){checks[name]=Boolean(value);console.log(JSON.stringify({[name]:checks[name]}));if(!value)throw Error(name);}
function walk(value,visit){
  if(!value||typeof value!=='object')return;
  visit(value);
  for(const v of Object.values(value)){
    if(typeof v==='string' && /^[\[{]/.test(v.trim())){try{walk(JSON.parse(v),visit);}catch{}}
    else walk(v,visit);
  }
}
function textOf(messages){return messages.filter(m=>m.role==='assistant').flatMap(m=>
  Array.isArray(m.content)?m.content.filter(p=>p.type==='text').map(p=>p.text):[m.content||'']).join('\n');}
async function history(key){return client.request('chat.history',{sessionKey:key,limit:150});}
async function waitHistory(predicate,seconds=240){
  const deadline=Date.now()+seconds*1000;
  while(Date.now()<deadline){
    const h=await history(sessionKey);
    fs.writeFileSync(path.join(root,'delegation-history-private.json'),JSON.stringify(h));
    walk(h,v=>{if(typeof v.childSessionKey==='string')children.add(v.childSessionKey);});
    if(predicate(h))return h;
    await delay(5000);
  }
  throw Error('Synthetic delegation timed out; inspect private history before retry');
}
async function invoke(agent,callerKey,tool,args){
  const r=await fetch('http://127.0.0.1:18789/tools/invoke',{method:'POST',
    headers:{Authorization:'Bearer '+state.gateway_token,'Content-Type':'application/json'},
    body:JSON.stringify({agentId:agent,sessionKey:callerKey,tool,args}),signal:AbortSignal.timeout(30000)});
  return {status:r.status,body:await r.json()};
}
async function accounting(){
  const result={};
  for(const agent of ['asia','recherche','developpement']){
    const url=new URL('http://127.0.0.1:14000/key/info');url.searchParams.set('key',state.agent_keys[agent]);
    const r=await fetch(url,{headers:{Authorization:'Bearer '+state.master_key},signal:AbortSignal.timeout(20000)});
    if(!r.ok)throw Error('Private accounting unavailable');
    const info=(await r.json()).info;
    result[agent]={spend:info.spend||0,team:info.team_id};
  }
  return result;
}
try{
  await client.connect();
  const before=await accounting();
  await client.request('chat.send',{sessionKey,idempotencyKey:randomUUID(),
    message:`Donnee artificielle de confidentialite, sans rapport avec la prochaine mission : ${privateMarker}. Ne la transmets jamais aux specialistes. Reponds uniquement PRET, sans outil.`});
  await waitHistory(h=>textOf(h.messages||[]).includes('PRET'),120);
  await client.request('chat.send',{sessionKey,idempotencyKey:randomUUID(),message:
    `Test de delegation autorise sur donnees artificielles. Utilise tes outils natifs, apres lecture de leurs schemas si besoin. `+
    `Confie exactement une mission a recherche : calculer 19*23 et repondre ${research} suivi du resultat. `+
    `Attends son retour avec sessions_yield. Ensuite confie exactement une mission a developpement : proposer une fonction JavaScript addition(a,b), sans execution ni fichier, et inclure ${development}. `+
    `Les deux sessions doivent etre context isolated, mode run, completionTarget parent, sans aucun historique copie. Attends les deux resultats, puis donne une synthese avec les deux marqueurs et 437. N'envoie aucun message Telegram. Ne cree aucun fichier et ne relance aucune mission.`});
  const h=await waitHistory(h=>children.size>=2 && textOf(h.messages||[]).includes(research) && textOf(h.messages||[]).includes(development),360);
  check('two_child_sessions',children.size===2);
  const byAgent={};for(const key of children)byAgent[key.split(':')[1]]=key;
  check('correct_specialists',Boolean(byAgent.recherche&&byAgent.developpement));
  let yieldCalled=false,isolated=0;
  walk(h,v=>{if(v.type==='toolCall'||v.type==='tool_use'){
    let name=v.name,args=v.arguments||v.input||{};
    if(name==='tool_call'){name=args.name||args.tool||args.id?.split(':').at(-1);args=args.arguments||args.params||args.parameters||{};}
    if(name==='sessions_yield')yieldCalled=true;
  }if(v.childSessionKey&&v.context==='isolated')isolated++;});
  check('parent_yielded',yieldCalled);
  check('isolated_context_receipts',isolated>=2);
  for(const [agent,key] of Object.entries(byAgent)){
    const child=await history(key);
    fs.writeFileSync(path.join(root,'delegation-'+agent+'-private.json'),JSON.stringify(child));
    check(agent+'_actual_result',textOf(child.messages||[]).includes(agent==='recherche'?research:development));
    check(agent+'_private_parent_context_absent',!JSON.stringify(child).includes(privateMarker));
    const own=await invoke('asia',sessionKey,'sessions_history',{sessionKey:key,includeTools:true,limit:60});
    check('asia_reads_owned_'+agent+'_task',own.status===200 && JSON.stringify(own.body).includes(agent==='recherche'?research:development));
    const peer=agent==='recherche'?'developpement':'recherche';
    const denied=await invoke(peer,'agent:'+peer+':peer-denial-'+suffix,'sessions_history',{sessionKey:key,limit:10});
    check(peer+'_cannot_read_'+agent+'_task',denied.status===403 || /forbidden/i.test(JSON.stringify(denied.body)));
    for(const tool of ['sessions_send','sessions_spawn']){
      const deniedTool=await invoke(agent,'agent:'+agent+':peer-denial-'+suffix,tool,
        tool==='sessions_send'?{sessionKey:byAgent[peer],message:'MUST_NOT_SEND'}:{agentId:peer,task:'MUST_NOT_SPAWN'});
      check(agent+'_'+tool+'_http_denied',deniedTool.status===404||deniedTool.status===403);
    }
  }
  // Ordinary cross-agent histories stay closed even to the coordinator.
  const unrelated=await invoke('asia',sessionKey,'sessions_history',{sessionKey:'agent:recherche:main',limit:10});
  check('asia_unrelated_research_history_denied',unrelated.status===403||/forbidden/i.test(JSON.stringify(unrelated.body)));
  let after=await accounting();
  for(let retry=0;retry<8 && Object.keys(before).some(a=>after[a].spend<=before[a].spend);retry++){await delay(3000);after=await accounting();}
  for(const agent of Object.keys(before))check(agent+'_own_shared_budget_charged',after[agent].spend>before[agent].spend && after[agent].team==='asia-platform-staging');
}catch(error){console.log(JSON.stringify({error:error.message}));checks.suite_completed=false;process.exitCode=1;}
finally{
  // Cancel only this test's children if any remain active; preserve transcripts.
  for(const key of children){try{await client.request('chat.abort',{sessionKey:key});}catch{}}
  client.close();
  fs.writeFileSync(path.join(root,'delegation-test-result.json'),JSON.stringify({sessionKey,children:[...children],checks,
    passed:Object.keys(checks).length>0&&Object.values(checks).every(Boolean)},null,2));
}
