// Real Asia -> Souleiman native task, private repository reads only, no Telegram delivery.
import fs from 'node:fs';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {GatewayClient,loadDevice} from './gateway-client.mjs';

const root=path.join(process.env.LOCALAPPDATA,'AsiaDocker');
const reportFile=path.join(root,'github-delegation-validation-private.json');
const saved=process.argv.includes('--verify-saved')?JSON.parse(fs.readFileSync(reportFile,'utf8')):null;
if(saved&&(!saved.childSessionKey||!saved.answer))throw Error('No completed delegation to verify');
const state=JSON.parse(fs.readFileSync(path.join(root,'runtime-private.json'),'utf8'));
const client=new GatewayClient({url:'ws://127.0.0.1:18789',token:state.gateway_token,
  device:loadDevice(path.join(root,'gateway-test-device.json'))});
const sessionKey=saved?.sessionKey||'agent:asia:github-delegation-test-'+randomUUID();
const report=saved||{sessionKey,startedAt:new Date().toISOString()};
const checks={};
const children=new Set(saved?.childSessionKey?[saved.childSessionKey]:[]);
const marker='DELEGATION_GITHUB_OK';
const readonly=['get_file_contents','get_commit','list_commits','list_branches','list_issues','issue_read',
  'list_pull_requests','pull_request_read','actions_list','actions_get','get_job_logs'].map(n=>'github__'+n);
const writes=['issue_write','create_pull_request','update_pull_request'].map(n=>'github__'+n);
function check(name,value){checks[name]=Boolean(value);console.log(JSON.stringify({[name]:checks[name]}));if(!value)throw Error(name);}
function walk(value,visit){
  if(!value||typeof value!=='object')return;
  visit(value);
  for(const v of Object.values(value)){
    if(typeof v==='string'){
      // Parse the host's untrusted-data wrapper without treating its content as instructions.
      const candidate=v.match(/<<<EXTERNAL_UNTRUSTED_CONTENT id="([^"]+)">>>\nSource: API\n---\n([\s\S]*)\n<<<END_EXTERNAL_UNTRUSTED_CONTENT id="\1">>>/)?.[2]||v;
      let parsed;try{parsed=JSON.parse(candidate);}catch{}if(parsed)walk(parsed,visit);
    }
    else walk(v,visit);
  }
}
const textOf=h=>(h.messages||[]).filter(m=>m.role==='assistant').flatMap(m=>
  Array.isArray(m.content)?m.content.filter(p=>p.type==='text').map(p=>p.text):[m.content||'']).join('\n');
const toolIds=effective=>(effective.groups||[]).flatMap(g=>g.tools||[]).map(t=>t.id);
function calls(h){
  const found=[];
  // Only this session's recorded calls. A sessions_history result can contain
  // another agent's transcript; counting it here would misattribute its calls.
  for(const v of (h.messages||[]).flatMap(m=>Array.isArray(m.content)?m.content:[])){
    if(v.type!=='toolCall'&&v.type!=='tool_use')continue;
    let name=v.name,args=v.arguments||v.input||{};
    if(name==='tool_call'){name=args.id?.split(':').at(-1)||name;args=args.args||{};}
    found.push({name,args});
  }
  return found;
}
async function expectedIssues(){
  const credential=execFileSync('git',['-c','credential.interactive=never','credential','fill'],{
    input:'protocol=https\nhost=github.com\n\n',encoding:'utf8',timeout:25000,windowsHide:true,
    env:{...process.env,GIT_TERMINAL_PROMPT:'0'},stdio:['pipe','pipe','pipe']});
  const token=credential.split(/\r?\n/).find(l=>l.startsWith('password='))?.slice(9);
  if(!token)throw Error('Existing Git authentication unavailable');
  let url='https://api.github.com/repos/Abdourahmandev/Simulateur_tax_qc/issues?state=all&per_page=100';
  const issues=[];
  while(url){
    const r=await fetch(url,{headers:{Authorization:'Bearer '+token,Accept:'application/vnd.github+json'},signal:AbortSignal.timeout(25000)});
    if(!r.ok)throw Error('GitHub baseline HTTP '+r.status);
    issues.push(...(await r.json()).filter(i=>!i.pull_request).map(i=>({number:i.number,title:i.title,state:i.state,body:i.body})));
    url=r.headers.get('link')?.split(',').find(l=>l.includes('rel="next"'))?.match(/<([^>]+)>/)?.[1];
  }
  return issues;
}
try{
  await client.connect();
  if(!saved){
    report.expected=await expectedIssues();
    report.status='submitting';fs.writeFileSync(reportFile,JSON.stringify(report));
    const ack=await client.request('chat.send',{sessionKey,idempotencyKey:randomUUID(),message:
      'Test technique autorise de delegation native en lecture seule. Confie exactement UNE mission a Souleiman (developpement), '+
      'runtime subagent, mode run, context isolated, completionTarget parent. Mission : lire le depot prive '+
      'https://github.com/Abdourahmandev/Simulateur_tax_qc via GitHub MCP natif, lister la racine avec get_file_contents '+
      '(fields name et type), puis TOUTES les issues ouvertes et fermees via list_issues avec perPage=2 pour tester la pagination. '+
      'Il doit consulter le schema, omettre state pour les deux etats, demander les champs number,title,body,state, '+
      'suivre endCursor tant que hasNextPage=true, et retourner numero, titre, etat et description breve de chaque issue, '+
      'avec nombre total et repartition ouvertes/fermees. Aucun fichier a modifier, aucune issue/PR/ticket/commentaire a creer, '+
      'aucun appel OpenCode, aucun message Telegram, aucune cle a demander. Ne lis pas GitHub toi-meme pour ce test. '+
      'Attends avec sessions_yield si expose ; sinon lis le schema de subagents et utilise action wait avec runIds, sans boucle de sondage. '+
      'Presente sa liste et les totaux, avec le marqueur '+marker+' uniquement apres son resultat verifie. '+
      'Si elle echoue, explique la limite sans nouvelle mission.'});
    report.runId=ack.runId;report.status='running';fs.writeFileSync(reportFile,JSON.stringify(report));
    const deadline=Date.now()+360000;
    while(Date.now()<deadline){
      report.parentHistory=await client.request('chat.history',{sessionKey,limit:150,maxChars:500000,maxBytes:2000000});
      walk(report.parentHistory,v=>{if(typeof v.childSessionKey==='string')children.add(v.childSessionKey);});
      if(children.size===1){report.childSessionKey=[...children][0];
        const h=await client.request('chat.history',{sessionKey:report.childSessionKey,limit:150,maxChars:500000,maxBytes:2000000});
        if(h.messages?.length)report.childHistory=h;
        // A child MCP connection is released when its run settles. Capture its live inventory.
        if(!report.childEffectiveLive){
          const effective=await client.request('tools.effective',{sessionKey:report.childSessionKey},70000);
          if(readonly.every(n=>toolIds(effective).includes(n))){
            report.childEffectiveLive=effective;report.childEffectiveAt=new Date().toISOString();
          }
        }
      }
      report.answer=textOf(report.parentHistory);
      fs.writeFileSync(reportFile,JSON.stringify(report));
      if(report.answer.includes(marker)&&report.childSessionKey)break;
      await new Promise(resolve=>setTimeout(resolve,4000));
    }
  }else{
    delete report.error;
    // Native children can be archived after completion. Keep the evidence captured live.
    if(!report.childHistory?.messages?.length)throw Error('Saved child trace missing; a new live test is required');
    const h=await client.request('chat.history',{sessionKey:report.childSessionKey,limit:150,maxChars:500000,maxBytes:2000000});
    if(h.messages?.length)report.childHistory=h;
  }
  check('parent_completed',report.answer.includes(marker));
  check('one_souleiman_child',children.size===1&&report.childSessionKey.startsWith('agent:developpement:subagent:'));
  const parentCalls=calls(report.parentHistory), childCalls=calls(report.childHistory);
  report.parentCalls=parentCalls;report.childCalls=childCalls;
  check('native_spawn_and_wait',parentCalls.some(c=>c.name==='sessions_spawn')&&parentCalls.some(c=>
    c.name==='sessions_yield'||c.name==='subagents'&&c.args.action==='wait'&&Array.isArray(c.args.runIds)));
  check('parent_did_not_read_github_itself',!parentCalls.some(c=>c.name.startsWith('github__')));
  check('child_read_private_repository',childCalls.some(c=>c.name==='github__get_file_contents'&&c.args.repo==='Simulateur_tax_qc'));
  check('child_followed_pagination',childCalls.some(c=>c.name==='github__list_issues'&&c.args.perPage===2)&&
    (report.expected.length<=2||childCalls.some(c=>c.name==='github__list_issues'&&c.args.after)));
  const received=new Map();let lastIssueArgs={};const completeStates=new Set();
  for(const message of report.childHistory.messages||[]){
    for(const call of calls({messages:[message]}))if(call.name==='github__list_issues')lastIssueArgs=call.args;
    if(message.role!=='toolResult')continue;
    walk(message,v=>{
      if(Array.isArray(v.issues)&&v.pageInfo?.hasNextPage===false){
        for(const state of lastIssueArgs.state?[lastIssueArgs.state]:['OPEN','CLOSED'])completeStates.add(state);
      }
      if(typeof v.number==='number'&&typeof v.title==='string')received.set(v.number,{...v,state:v.state||lastIssueArgs.state});
    });
  }
  check('both_issue_states_fully_paginated',completeStates.has('OPEN')&&completeStates.has('CLOSED'));
  check('all_issue_titles_and_bodies_read',report.expected.length>0&&report.expected.every(i=>{
    const r=received.get(i.number);return r?.title===i.title&&r.state?.toLowerCase()===i.state&&(r.body||'')===(i.body||'');
  }));
  check('parent_report_contains_all_issues',report.expected.every(i=>report.answer.includes(i.title)));
  const expectedCalls=['tool_search','tool_describe','github__get_file_contents','github__list_issues','github__issue_read'];
  check('child_only_used_read_tools',childCalls.every(c=>expectedCalls.includes(c.name)));
  check('child_tool_results_succeeded',(report.childHistory.messages||[])
    .filter(m=>m.role==='toolResult').every(m=>m.isError===false));
  report.effective={};
  for(const [name,key] of [['asia',sessionKey],['child',report.childSessionKey]]){
    const effective=name==='child'&&report.childEffectiveLive?report.childEffectiveLive:
      await client.request('tools.effective',{sessionKey:key},70000);
    report.effective[name]=effective;const ids=toolIds(effective);
    check(name+'_github_reads_available',readonly.every(n=>ids.includes(n)));
    check(name+'_github_pr_creation_available',ids.includes('github__create_pull_request'));
    check(name+'_github_other_writes_absent',writes.filter(n=>n!=='github__create_pull_request').every(n=>!ids.includes(n)));
    check(name+'_context7_available',ids.includes('context7__query-docs')&&ids.includes('context7__resolve-library-id'));
  }
  const inventory=await client.request('sessions.list',{limit:200});
  for(const agent of ['developpement','recherche']){
    const session=inventory.sessions?.find(s=>s.agentId===agent&&!s.key.includes(':subagent:'));
    if(!session)throw Error('Missing direct session for '+agent);
    const effective=await client.request('tools.effective',{sessionKey:session.key},70000);
    report.effective[agent]=effective;const ids=toolIds(effective);
    if(agent==='developpement')check('direct_souleiman_keeps_selected_writes',writes.every(n=>ids.includes(n)));
    else check('saredo_connectors_absent',!ids.some(n=>/^(github|context7)__/.test(n)));
  }
  report.health=await client.request('health',{},70000);
  check('gateway_health',report.health.ok===true);
  check('three_telegram_accounts_running',['asia','developpement','recherche'].every(a=>{
    const account=report.health.channels?.telegram?.accounts?.[a];
    return account?.configured===true&&account.running===true&&account.lastError===null;
  }));
  report.status='passed';
}catch(e){report.error=e.message;report.status='failed';process.exitCode=1;console.log(JSON.stringify({error:e.message}));
  for(const key of [sessionKey,...children]){try{await client.request('chat.abort',{sessionKey:key});}catch{}}
}finally{client.close();report.checks=checks;report.finishedAt=new Date().toISOString();fs.writeFileSync(reportFile,JSON.stringify(report,null,2));}
