// Read-only integration and real agent turn. No Telegram delivery or GitHub mutation.
import fs from 'node:fs';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {GatewayClient,loadDevice} from './gateway-client.mjs';

const root=path.join(process.env.LOCALAPPDATA,'AsiaDocker');
const reportFile=path.join(root,'souleiman-connectors-validation-private.json');
const saved=process.argv.includes('--verify-saved')?JSON.parse(fs.readFileSync(reportFile,'utf8')):null;
if(saved&&(!saved.checks?.agent_completed||!saved.history||!saved.sessionKey?.startsWith('agent:developpement:connectors-test-')))throw Error('No completed connector test to verify');
const state=JSON.parse(fs.readFileSync(path.join(root,'runtime-private.json'),'utf8'));
const client=new GatewayClient({url:'ws://127.0.0.1:18789',token:state.gateway_token,
  device:loadDevice(path.join(root,'gateway-test-device.json'))});
const sessionKey=saved?.sessionKey||'agent:developpement:connectors-test-'+randomUUID();
const checks={};
const report=saved||{sessionKey,startedAt:new Date().toISOString()};
if(saved?.error){report.previousTestError=saved.error;delete report.error;}
function check(name,value){checks[name]=Boolean(value);console.log(JSON.stringify({[name]:checks[name]}));if(!value)throw Error('Failed: '+name);}
try{
  await client.connect();
  if(!saved){
  // /tools/invoke resolves synchronous core/plugin tools, not dynamic MCP tools.
  // Verify transports separately, then prove availability through a real agent turn.
  const transport=JSON.parse(execFileSync('docker',['exec','-i','asia-platform-staging-openclaw-1','node','--input-type=module'],{
    input:fs.readFileSync(new URL('./test-souleiman-mcp-transports.mjs',import.meta.url)),encoding:'utf8',timeout:120000,windowsHide:true}));
  report.transports=transport;check('mcp_transports_passed',transport.passed);
  const marker='CONNECTORS_VERIFIED_'+randomUUID().slice(0,8);
  const events=[];
  client.onEvent(e=>{if(e.event==='chat'&&e.payload?.sessionKey===sessionKey)events.push(e.payload);});
  report.status='submitting';fs.writeFileSync(reportFile,JSON.stringify(report));
  const ack=await client.request('chat.send',{sessionKey,idempotencyKey:randomUUID(),message:
    'Test technique en lecture seule de tes nouveaux connecteurs. Utilise tool_search puis tool_describe si necessaire. '+
    '1. Appelle context7__query-docs, libraryId=/microsoft/playwright, question generale: comment verifier le titre d une page avec Playwright Test ? '+
    '2. Appelle github__get_file_contents pour owner=Abdourahmandev, repo=Platforme_agentique, path=package.json, ref=refs/heads/main. '+
    'Aucun fichier a modifier, aucune issue/PR a creer, aucun message Telegram ni appel OpenCode. '+
    'Ne communique aucun contenu du depot a Context7. Termine avec le nom du package lu dans GitHub et la methode Playwright trouvee, puis '+marker+'.'});
  report.runId=ack.runId;report.status='running';fs.writeFileSync(reportFile,JSON.stringify(report));
  const deadline=Date.now()+240000;
  let history,finished=false;
  while(Date.now()<deadline){
    history=await client.request('chat.history',{sessionKey,limit:80});
    const outputs=(history.messages||[]).filter(m=>m.role==='assistant').map(m=>typeof m.content==='string'?m.content:(m.content||[]).filter(p=>p.type==='text').map(p=>p.text).join('\n'));
    if(outputs.at(-1)?.includes(marker)){report.answer=outputs.at(-1);finished=true;break;}
    if(events.some(e=>['error','aborted'].includes(e.state)))throw Error('Agent run failed');
    await new Promise(resolve=>setTimeout(resolve,2500));
  }
  report.history=history;
  check('agent_completed',finished);
  }else{
    check('mcp_transports_passed',report.transports?.passed===true);
    report.history=await client.request('chat.history',{sessionKey,limit:80});
    check('agent_completed',report.answer?.includes('CONNECTORS_VERIFIED_'));
  }
  const calls=(report.history.messages||[]).flatMap(m=>Array.isArray(m.content)?m.content:[])
    .filter(p=>p.type==='toolCall'||p.type==='tool_use');
  report.toolCalls=calls.map(p=>({name:p.name,arguments:p.arguments||p.input}));
  const names=report.toolCalls.map(p=>p.name);
  check('agent_called_context7',names.includes('context7__query-docs'));
  check('agent_called_github',names.includes('github__get_file_contents'));
  const results=report.history.messages.filter(m=>m.role==='toolResult');
  check('agent_tool_results_succeeded',results.length>=2&&results.every(m=>m.isError===false));
  check('agent_report_matches_sources',report.answer.includes('asia-agent-app')&&report.answer.includes('toHaveTitle'));
  const allowed=['tool_search','tool_describe','context7__resolve-library-id','context7__query-docs','github__get_file_contents'];
  // The deferred MCP runtime records both tool_call and the underlying MCP call.
  check('agent_used_only_expected_tools',report.toolCalls.every(p=>allowed.includes(p.name)||
    p.name==='tool_call'&&['mcp:context7:context7__resolve-library-id','mcp:context7:context7__query-docs','mcp:github:github__get_file_contents'].includes(p.arguments?.id)));
  const effective=await client.request('tools.effective',{sessionKey},70000);
  report.effective=effective;
  const toolIds=value=>(value.groups||[]).flatMap(g=>g.tools||[]).map(t=>t.id);
  const ids=toolIds(effective);
  check('soulei_context7_available',ids.includes('context7__query-docs'));
  check('context7_exactly_two_tools',ids.filter(n=>n.startsWith('context7__')).length===2);
  check('soulei_github_available',ids.includes('github__get_file_contents')&&ids.includes('github__actions_list'));
  check('github_merge_not_exposed',!ids.includes('github__merge_pull_request'));
  check('github_exactly_fourteen_tools',ids.filter(n=>n.startsWith('github__')).length===14);
  const inventory=await client.request('sessions.list',{limit:200});
  report.otherAgents={};
  for(const agent of ['asia','recherche']){
    const session=inventory.sessions?.find(s=>s.agentId===agent&&!s.key.includes(':subagent:'));
    if(!session)throw Error('Missing existing session for '+agent);
    const tools=toolIds(await client.request('tools.effective',{sessionKey:session.key},70000));
    report.otherAgents[agent]={connectors:tools.filter(n=>/^(context7|github)__/.test(n))};
    if(agent==='recherche')check('saredo_new_connectors_unavailable',report.otherAgents[agent].connectors.length===0);
    else {
      check('asia_read_connectors_available',tools.includes('github__list_issues')&&tools.includes('context7__query-docs'));
      check('asia_github_writes_unavailable',['issue_write','create_pull_request','update_pull_request']
        .every(name=>!tools.includes('github__'+name)));
    }
  }
  const health=await client.request('health',{},70000);
  report.health=health;
  check('gateway_health',health.ok===true);
  check('three_telegram_accounts_running',['asia','developpement','recherche'].every(agent=>{
    const account=health.channels?.telegram?.accounts?.[agent];
    return account?.configured===true&&account.running===true&&account.lastError===null;
  }));
  report.status='passed';
}catch(e){report.error=e.message;report.status='failed';process.exitCode=1;console.log(JSON.stringify({error:e.message}));
  try{await client.request('chat.abort',{sessionKey});}catch{}
}finally{client.close();report.checks=checks;report.finishedAt=new Date().toISOString();fs.writeFileSync(reportFile,JSON.stringify(report,null,2));}
