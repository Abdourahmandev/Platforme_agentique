// Fixed synthetic Windows command only. Never approve a model-produced command.
import fs from 'node:fs';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {GatewayClient,loadDevice} from './gateway-client.mjs';

const root = path.join(process.env.LOCALAPPDATA,'AsiaDocker');
const privateState = JSON.parse(fs.readFileSync(path.join(root,'runtime-private.json'),'utf8'));
const headers = {Authorization:'Bearer ' + privateState.gateway_token,'Content-Type':'application/json'};
const client = new GatewayClient({url:'ws://127.0.0.1:18789',token:privateState.gateway_token,device:loadDevice(path.join(root,'gateway-test-device.json')),caps:['plugin-approvals']});
const agentId = process.argv.includes('--souleiman') ? 'developpement' : 'asia';
const fileTest = process.argv.includes('--files');
if (fileTest && agentId !== 'developpement') throw Error('--files requires --souleiman');
const sessionKey = 'agent:' + agentId + ':migration-bridge-' + randomUUID();
const marker = fileTest ? 'SOULEIMAN_FILES_' + randomUUID().slice(0,8) : agentId === 'asia' ? 'ASIA_BRIDGE_TEST' : 'SOULEIMAN_WINDOWS_TEST';
const command = fileTest ? `node -e "const f=require('fs'),p=require('path').join(require('os').tmpdir(),'${marker}.txt');f.writeFileSync(p,'${marker}');console.log(f.readFileSync(p,'utf8'));f.unlinkSync(p)"` : 'echo ' + marker;
const checks = {};
let taskId;
const delay = ms => new Promise(resolve => setTimeout(resolve,ms));
const check = (name, value) => {checks[name] = Boolean(value); console.log(JSON.stringify({[name]:checks[name]})); if (!value) throw Error('Failed: ' + name);};
async function invoke(args, targetAgent = agentId) {
  const response = await fetch('http://127.0.0.1:18789/tools/invoke',{
    method:'POST',headers,body:JSON.stringify({tool:'asia_opencode_task',agentId:targetAgent,sessionKey:targetAgent === agentId ? sessionKey : 'agent:' + targetAgent + ':migration-bridge-test',args}),signal:AbortSignal.timeout(45000),
  });
  const body = await response.json();
  if (targetAgent !== agentId) return {http:response.status, isError:body.result?.isError, details:body.result?.details};
  if (!response.ok || body.result?.isError) throw Error('Bridge operation failed: ' + JSON.stringify(body).slice(0,500));
  return body.result.details;
}
async function waitStatus(predicate) {
  const deadline = Date.now() + 150000;
  while (Date.now() < deadline) {
    const status = await invoke({action:'status',taskId});
    if (predicate(status)) return status;
    await delay(2000);
  }
  throw Error('OpenCode fixture timed out');
}
async function decision(permissionId, choice) {
  // Separate synthetic conversations: a prior refusal must not be treated as
  // an instruction to retry the same tool call in a real conversation.
  const approvalSessionKey = sessionKey + ':' + choice;
  const terminal = [];
  const unsubscribe = client.onEvent(event => {if(event.event === 'chat' && event.payload?.sessionKey === approvalSessionKey && ['final','error','aborted'].includes(event.payload.state)) terminal.push(event.payload);});
  await client.request('chat.send',{sessionKey:approvalSessionKey,
    message:`Test technique. Utilise tool_search puis tool_describe si necessaire, puis appelle exactement asia_opencode_approve avec taskId=${taskId} et permissionId=${permissionId}. Le proprietaire utilise la surface native pour valider ou refuser. N appelle aucun autre outil ni aucune autre tache.`,
    idempotencyKey:randomUUID(),
  });
  const deadline = Date.now() + 125000;
  while (Date.now() < deadline) {
    const list = await client.request('plugin.approval.list');
    fs.writeFileSync(path.join(root,'bridge-approval-private.json'),JSON.stringify(list));
    const rows = Array.isArray(list) ? list : list.approvals || list.requests || [];
    const approval = rows.find(row => row.request?.sessionKey === approvalSessionKey && row.request?.toolName === 'asia_opencode_approve');
    if (approval) {
      const request = approval.request;
      // Fail closed: this test must never grant permission to a different action.
      if (request.description !== 'bash: ' + JSON.stringify([command]) || request.agentId !== agentId) throw Error('Unexpected approval request');
      check('native_' + choice + '_offered',request.allowedDecisions.includes(choice) && !request.allowedDecisions.includes('allow-always'));
      await client.request('plugin.approval.resolve',{id:approval.id,decision:choice});
      unsubscribe();
      return;
    }
    if (terminal.length) {unsubscribe();throw Error('Agent ended without requesting native approval');}
    await delay(1500);
  }
  unsubscribe();
  throw Error('Native approval not observed');
}
try {
  await client.connect();
  check('recherche_bridge_denied',(await invoke({action:'status',taskId:'synthetic0001'},'recherche')).http === 404);
  // A training identity is not registered on production: the Gateway rejects
  // its session before tool lookup (400), rather than reporting a missing tool.
  check('unknown_training_agent_denied',(await invoke({action:'status',taskId:'synthetic0001'},'formation-developpement')).http === 400);
  const request = {action:'start',requestId:randomUUID(),prompt:`Test technique artificiel : execute exactement la commande bash suivante, sans la reformuler ni ajouter d autre commande :\n${command}\nAttends l autorisation si demandee. ${fileTest ? 'Le seul fichier autorise est le fichier temporaire unique indique dans cette commande, pour ecriture, relecture et suppression.' : 'Ne lis et ne modifie aucun fichier.'} Termine avec la sortie exacte de la commande.`};
  const started = await invoke(request); taskId = started.taskId;
  check('task_accepted',started.submission === 'accepted');
  const other = await invoke({action:'status',taskId},agentId === 'asia' ? 'developpement' : 'asia');
  check('other_agent_cannot_read_task',other.isError === true);
  const repeated = await invoke(request);
  check('no_duplicate_submission',repeated.taskId === taskId && repeated.repeated);
  const waiting = await waitStatus(s => s.permissions.length > 0);
  const permission = waiting.permissions.find(p => p.permission === 'bash' && JSON.stringify(p.patterns) === JSON.stringify([command]));
  check('windows_action_waits',Boolean(permission) && !waiting.completed);
  await decision(permission.id,'deny');
  await delay(2000);
  const denied = await invoke({action:'status',taskId});
  check('denial_does_not_execute',denied.permissions.some(p => p.id === permission.id) && !denied.completed);
  // Allow the first OpenClaw turn to settle before starting a second.
  await delay(5000);
  await decision(permission.id,'allow-once');
  const done = await waitStatus(s => s.completed && !s.permissions.length && s.status === 'idle');
  check('approved_echo_completed',done.text.includes(marker));
  const traceCode=`import fs from 'node:fs';const {Bridge,bridgeStateFile}=await import('/home/node/.openclaw/extensions/asia-opencode/bridge.mjs');const b=new Bridge({agentId:process.argv[1],stateFile:bridgeStateFile('/home/node/.openclaw',process.argv[1]),credentials:()=>JSON.parse(fs.readFileSync('/home/node/.openclaw/credentials/asia-opencode.json'))});const task=b.own(process.argv[2]);console.log(JSON.stringify(await b.request('/session/'+task.sessionId+'/message')));`;
  const trace=JSON.parse(execFileSync((process.platform === 'win32' ? 'C:\\Program Files\\Docker\\Docker\\resources\\bin\\docker.exe' : 'docker'),
    ['exec','asia-platform-staging-openclaw-1','node','--input-type=module','-e',traceCode,agentId,taskId],{encoding:'utf8',windowsHide:true,timeout:35000}));
  const calls=trace.flatMap(m=>(m.parts||[]).filter(p=>p.type==='tool'));
  check('real_windows_command_executed_once',calls.length===1&&calls[0].tool==='bash'&&calls[0].state?.input?.command===command&&calls[0].state?.status==='completed'&&calls[0].state?.output?.trim()===marker);
  if(fileTest)check('temporary_file_removed',!fs.existsSync(path.join(process.env.TEMP,marker+'.txt')));
} catch (error) {
  console.log(JSON.stringify({error:error.message}));
  checks.suite_completed = false;
  process.exitCode = 1;
} finally {
  if (taskId) {
    try {await invoke({action:'cancel',taskId});checks.fixture_stopped = true;} catch {checks.fixture_stopped = false;process.exitCode = 1;}
  }
  client.close();
  fs.writeFileSync(path.join(root,agentId === 'asia' ? 'opencode-bridge-result.json' : 'opencode-bridge-'+agentId+(fileTest?'-files':'')+'-result.json'),JSON.stringify({agentId,sessionKey,taskId,at:new Date().toISOString(),checks,passed:Object.keys(checks).length > 0 && Object.values(checks).every(Boolean)},null,2));
}
