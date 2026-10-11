// Synthetic Windows echo only. Never approve arbitrary model-produced commands.
import fs from 'node:fs';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {GatewayClient,loadDevice} from './gateway-client.mjs';

const root = path.join(process.env.LOCALAPPDATA,'AsiaDocker');
const privateState = JSON.parse(fs.readFileSync(path.join(root,'runtime-private.json'),'utf8'));
const headers = {Authorization:'Bearer ' + privateState.gateway_token,'Content-Type':'application/json'};
const client = new GatewayClient({url:'ws://127.0.0.1:18789',token:privateState.gateway_token,device:loadDevice(path.join(root,'gateway-test-device.json')),caps:['plugin-approvals']});
const sessionKey = 'agent:asia:migration-bridge-' + randomUUID();
const checks = {};
let taskId;
const delay = ms => new Promise(resolve => setTimeout(resolve,ms));
const check = (name, value) => {checks[name] = Boolean(value); console.log(JSON.stringify({[name]:checks[name]})); if (!value) throw Error('Failed: ' + name);};
async function invoke(args, agentId = 'asia') {
  const response = await fetch('http://127.0.0.1:18789/tools/invoke',{
    method:'POST',headers,body:JSON.stringify({tool:'asia_opencode_task',agentId,sessionKey:agentId === 'asia' ? sessionKey : 'agent:' + agentId + ':migration-bridge-test',args}),signal:AbortSignal.timeout(45000),
  });
  const body = await response.json();
  if (agentId !== 'asia') return {http:response.status};
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
      if (request.description !== 'bash: ["echo ASIA_BRIDGE_TEST"]' || request.agentId !== 'asia') throw Error('Unexpected approval request');
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
  for (const agent of ['developpement','recherche']) check(agent + '_bridge_denied',(await invoke({action:'status',taskId:'synthetic0001'},agent)).http === 404);
  const request = {action:'start',requestId:randomUUID(),prompt:'Test technique artificiel : execute exactement la commande bash echo ASIA_BRIDGE_TEST. Attends l autorisation si demandee. Ne lis et ne modifie aucun fichier. Termine avec la sortie exacte de la commande.'};
  const started = await invoke(request); taskId = started.taskId;
  check('task_accepted',started.submission === 'accepted');
  const repeated = await invoke(request);
  check('no_duplicate_submission',repeated.taskId === taskId && repeated.repeated);
  const waiting = await waitStatus(s => s.permissions.length > 0);
  const permission = waiting.permissions.find(p => p.permission === 'bash' && JSON.stringify(p.patterns) === '["echo ASIA_BRIDGE_TEST"]');
  check('windows_action_waits',Boolean(permission) && !waiting.completed);
  await decision(permission.id,'deny');
  await delay(2000);
  const denied = await invoke({action:'status',taskId});
  check('denial_does_not_execute',denied.permissions.some(p => p.id === permission.id) && !denied.completed);
  // Allow the first OpenClaw turn to settle before starting a second.
  await delay(5000);
  await decision(permission.id,'allow-once');
  const done = await waitStatus(s => s.completed && !s.permissions.length && s.status === 'idle');
  check('approved_echo_completed',done.text.includes('ASIA_BRIDGE_TEST'));
} catch (error) {
  console.log(JSON.stringify({error:error.message}));
  checks.suite_completed = false;
  process.exitCode = 1;
} finally {
  if (taskId) {
    try {await invoke({action:'cancel',taskId});checks.fixture_stopped = true;} catch {checks.fixture_stopped = false;process.exitCode = 1;}
  }
  client.close();
  fs.writeFileSync(path.join(root,'opencode-bridge-result.json'),JSON.stringify({checks,passed:Object.keys(checks).length > 0 && Object.values(checks).every(Boolean)},null,2));
}
