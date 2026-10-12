// Live name/delegation checks in private synthetic sessions. No Telegram delivery.
import fs from 'node:fs';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {GatewayClient,loadDevice} from './gateway-client.mjs';
const root=path.join(process.env.LOCALAPPDATA,'AsiaDocker');
const privateDir=path.join(process.env.LOCALAPPDATA,'AsiaPaperclip');
const state=JSON.parse(fs.readFileSync(path.join(root,'runtime-private.json'),'utf8'));
const client=new GatewayClient({url:'ws://127.0.0.1:18789',token:state.gateway_token,
  device:loadDevice(path.join(root,'gateway-test-device.json'))});
const run=randomUUID(),checks={},sessions=[],children=new Set();
const resultFile=path.join(privateDir,'agent-names-live-'+run+'.json');
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
function check(name,value){checks[name]=Boolean(value);console.log(JSON.stringify({[name]:checks[name]}));if(!value)throw Error(name);}
function walk(value,visit){if(!value||typeof value!=='object')return;visit(value);for(const v of Object.values(value)){
  if(typeof v==='string'&&/^[\[{]/.test(v.trim())){try{walk(JSON.parse(v),visit);}catch{}}else walk(v,visit);
}}
function assistantText(h){return (h.messages||[]).filter(m=>m.role==='assistant').flatMap(m=>
  Array.isArray(m.content)?m.content.filter(c=>c.type==='text').map(c=>c.text):[m.content||'']).join('\n');}
async function history(key){return client.request('chat.history',{sessionKey:key,limit:150});}
async function waitHistory(key,predicate,seconds){
  const deadline=Date.now()+seconds*1000;
  while(Date.now()<deadline){const h=await history(key);fs.writeFileSync(path.join(privateDir,'agent-names-history-'+key.split(':')[1]+'-'+run+'.json'),JSON.stringify(h));
    if(predicate(h))return h;await sleep(4000);}
  throw Error('Live response timed out; inspect saved sessions before repeating');
}
try{
  await client.connect();
  const channels=await client.request('channels.status',{probe:true,timeoutMs:10000});
  for(const aid of ['asia','developpement','recherche']){
    const c=(channels.channelAccounts?.telegram||[]).find(c=>c.accountId===aid);
    check(aid+'_telegram_health',c?.running===true&&c?.probe?.ok===true);
  }
  for(const [aid,name] of (process.argv.includes('--delegation-only')?[]:[['developpement','Souleiman'],['recherche','Saredo']])){
    const key='agent:'+aid+':name-check-'+run;sessions.push(key);
    await client.request('chat.send',{sessionKey:key,idempotencyKey:randomUUID(),
      message:'Test autorise de ton identite actuelle. Presente-toi en une phrase avec ton nom actuel et ton role, sans outil, sans fichier, sans contacter qui que ce soit. Ajoute IDENTITE_OK.'});
    const h=await waitHistory(key,h=>assistantText(h).includes('IDENTITE_OK'),120);
    check(aid+'_self_identifies',assistantText(h).includes(name));
  }
  const parent='agent:asia:name-delegation-'+run;sessions.push(parent);
  const markerR='NOM_RECHERCHE_'+run,markerD='NOM_DEV_'+run;
  await client.request('chat.send',{sessionKey:parent,idempotencyKey:randomUUID(),message:
    `Test autorise de delegation avec les nouveaux noms. Confie a Saredo une seule mission : donner son nom actuel et calculer 19*23, avec le marqueur ${markerR}. `+
    `Apres son retour, confie a Souleiman une seule mission : donner son nom actuel et proposer la fonction JavaScript addition(a,b), sans execution, avec ${markerD}. `+
    'Utilise les outils natifs et les identifiants stables de ces deux collegues. IMPORTANT pour conserver les preuves du test : sessions_spawn doit utiliser cleanup="keep" et runTimeoutSeconds=180 pour chaque mission; ne supprime ni n archive les sessions. Attends les retours par sessions_yield puis synthetise leurs deux reponses avec leurs noms et marqueurs. Aucune creation de ticket, aucun fichier, aucun message Telegram, aucune repetition de mission.'});
  const h=await waitHistory(parent,h=>{
    walk(h,v=>{if(typeof v.childSessionKey==='string')children.add(v.childSessionKey);});
    const text=assistantText(h);return children.size>=2&&text.includes(markerR)&&text.includes(markerD);
  },360);
  check('exactly_two_delegated_sessions',children.size===2);
  const byAgent=Object.fromEntries([...children].map(k=>[k.split(':')[1],k]));
  check('stable_delegation_destinations',Boolean(byAgent.recherche&&byAgent.developpement));
  for(const [aid,name,marker] of [['recherche','Saredo',markerR],['developpement','Souleiman',markerD]]){
    const child=await history(byAgent[aid]);fs.writeFileSync(path.join(privateDir,'agent-names-child-'+aid+'-'+run+'.json'),JSON.stringify(child));
    check(aid+'_delegated_result',assistantText(child).includes(name)&&assistantText(child).includes(marker));
  }
  check('asia_synthesis_new_names',assistantText(h).includes('Souleiman')&&assistantText(h).includes('Saredo')&&assistantText(h).includes('437'));
  const baseline=JSON.parse(fs.readFileSync(path.join(privateDir,'agent-names-session-baseline-private.json'),'utf8'));
  const now=await client.request('sessions.list',{limit:300});
  check('previous_sessions_retained',(baseline.sessions||[]).every(b=>(now.sessions||[]).some(n=>n.key===b.key&&n.sessionId===b.sessionId)));
}catch(error){checks.completed=false;console.log(JSON.stringify({error:error.message}));process.exitCode=1;}
finally{
  client.close();
  fs.writeFileSync(resultFile,JSON.stringify({run,sessions,children:[...children],checks,passed:Object.values(checks).length>0&&Object.values(checks).every(Boolean)},null,2));
  console.log(JSON.stringify({privateReceipt:path.basename(resultFile)}));
}
