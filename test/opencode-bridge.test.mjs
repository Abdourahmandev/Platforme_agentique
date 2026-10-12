import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {Bridge, assertBridgeAgent, bridgeStateFile} from '../infra/opencode-bridge/bridge.mjs';
import plugin from '../infra/opencode-bridge/index.mjs';

function fixture(t, agentId = 'asia') {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(),'asia-bridge-'));
  t.after(() => fs.rmSync(dir, {recursive:true,force:true}));
  const calls = [], pending = [{id:'per_test0001',sessionID:'ses_test0001',permission:'bash',patterns:['echo synthetic']}];
  let failPrompt = false;
  const options = {agentId,stateFile:bridgeStateFile(dir,agentId), credentials:() => ({username:'fixture',password:'fixture',directory:'C:/synthetic'}),
    fetchImpl:async (url, opts) => {
      const body = opts.body && JSON.parse(opts.body);
      calls.push({route:url.pathname, body});
      if (url.pathname.endsWith('prompt_async') && failPrompt) throw Error('connection reset');
      const result = url.pathname === '/session' ? {id:'ses_test0001'} : url.pathname === '/permission' ? pending : {};
      return new Response(JSON.stringify(result));
    }};
  const bridge = new Bridge(options);
  return {bridge, options, calls, pending, fail:() => {failPrompt = true;}};
}

test('bridge isolates tasks and rejects untrusted agent context', async t => {
  const f = fixture(t);
  assert.equal(assertBridgeAgent({agentId:'developpement'}),'developpement');
  assert.throws(() => assertBridgeAgent({agentId:'recherche'}));
  assert.throws(() => assertBridgeAgent({}));
  await assert.rejects(f.bridge.status('ses_test0001'), /inconnue/);
  assert.equal(f.calls.length, 0);
});
test('submission is idempotent across concurrent calls and restarts', async t => {
  const f = fixture(t), input = {action:'start',requestId:'request0001',prompt:'test'};
  const [first, repeated] = await Promise.all([f.bridge.mutate(input),f.bridge.mutate(input)]);
  assert.equal(first.taskId,repeated.taskId);
  const restarted = new Bridge(f.options);
  assert.equal((await restarted.mutate(input)).repeated,true);
  assert.equal(f.calls.filter(c => c.route.endsWith('prompt_async')).length,1);
  await assert.rejects(restarted.mutate({...input,prompt:'different'}), /deja utilise/);
});
test('uncertain prompt submission cannot be replayed', async t => {
  const f = fixture(t), input = {action:'start',requestId:'request0002',prompt:'test'};
  f.fail();
  await assert.rejects(f.bridge.mutate(input), /incertain/);
  assert.equal((await new Bridge(f.options).mutate(input)).submission,'uncertain');
  assert.equal(f.calls.filter(c => c.route.endsWith('prompt_async')).length,1);
});
test('model cannot approve itself, spoof another request, or reuse a native grant', async t => {
  const f = fixture(t);
  const task = await f.bridge.mutate({action:'start',requestId:'request0003',prompt:'test'});
  const params = {taskId:task.taskId,permissionId:'per_test0001'};
  await assert.rejects(f.bridge.approve('call_001', params),/humaine/);
  const event = {toolName:'asia_opencode_approve',toolCallId:'call_001',params};
  const hook = await f.bridge.approvalHook(event,{agentId:'asia'});
  assert.deepEqual(hook.requireApproval.allowedDecisions,['allow-once','deny']);
  hook.requireApproval.onResolution('deny');
  await assert.rejects(f.bridge.approve('call_001', params),/humaine/);
  hook.requireApproval.onResolution('allow-once');
  // Real OpenClaw hooks and tool factories load separate module instances.
  assert.deepEqual(await new Bridge(f.options).approve('call_001',{permissionId:params.permissionId,taskId:params.taskId}),{approvedOnce:true});
  await assert.rejects(f.bridge.approve('call_001',params),/humaine/);
  assert.equal(f.calls.filter(c => c.body?.reply === 'once').length,1);
  assert.equal((await f.bridge.approvalHook(event,{agentId:'developpement'})).block,true);
});
test('changed or expired permission cannot consume approval', async t => {
  const f = fixture(t);
  const task = await f.bridge.mutate({action:'start',requestId:'request0004',prompt:'test'});
  const params = {taskId:task.taskId,permissionId:'per_test0001'};
  const hook = await f.bridge.approvalHook({toolName:'asia_opencode_approve',toolCallId:'call_002',params},{agentId:'asia'});
  hook.requireApproval.onResolution('allow-once');
  f.pending[0].patterns = ['different action'];
  await assert.rejects(f.bridge.approve('call_002',params),/change/);
  const retry = await f.bridge.approvalHook({toolName:'asia_opencode_approve',toolCallId:'call_003',params},{agentId:'asia'});
  retry.requireApproval.onResolution('allow-once');
  const receipt = f.bridge.grantPath('call_003');
  const grant = JSON.parse(fs.readFileSync(receipt));
  grant.until = Date.now() - 1;
  fs.writeFileSync(receipt,JSON.stringify(grant));
  await assert.rejects(f.bridge.approve('call_003',params),/humaine/);
  assert.equal(f.calls.filter(c => c.body?.reply).length,0);
});
test('separate plugin instances cannot race journal writes or approve after a crash lock', async t => {
  const f = fixture(t);
  await f.bridge.serial(async () => {
    await assert.rejects(new Bridge(f.options).mutate({action:'start',requestId:'request0010',prompt:'test'}),/verrou/);
  });
  assert.equal(f.calls.length,0);
});

test('specialists get independent task journals and cannot consume Asia approvals', async t => {
  const asia = fixture(t), dev = fixture(t,'developpement');
  const input = {action:'start',requestId:'same-request',prompt:'test'};
  const a = await asia.bridge.mutate(input), d = await dev.bridge.mutate(input);
  assert.notEqual(a.taskId,d.taskId);
  assert.match(dev.calls.find(c=>c.route==='/session').body.title,/^Souleiman \/ /);
  for (const [f,foreign] of [[asia,d],[dev,a]]) {
    const count=f.calls.length;
    await assert.rejects(f.bridge.status(foreign.taskId),/inconnue/);
    for (const action of ['cancel','reject','answer','continue']) {
      await assert.rejects(f.bridge.mutate({action,taskId:foreign.taskId,requestId:'foreign-request',prompt:'test'}),/inconnue/);
    }
    assert.equal(f.calls.length,count);
  }
  const params={taskId:a.taskId,permissionId:'per_test0001'};
  const hook=await asia.bridge.approvalHook({toolName:'asia_opencode_approve',toolCallId:'same-call',params},{agentId:'asia'});
  hook.requireApproval.onResolution('allow-once');
  await assert.rejects(dev.bridge.approve('same-call',{taskId:d.taskId,permissionId:'per_test0001'}),/humaine/);
  assert.deepEqual(await asia.bridge.approve('same-call',params),{approvedOnce:true});
});

test('Souleiman approval survives reload but is bound to his native context', async t => {
  const f=fixture(t,'developpement');
  const task=await f.bridge.mutate({action:'start',requestId:'dev-request',prompt:'test'});
  const event={toolName:'asia_opencode_approve',toolCallId:'dev-call',params:{taskId:task.taskId,permissionId:'per_test0001'}};
  assert.equal((await f.bridge.approvalHook(event,{agentId:'asia'})).block,true);
  const hook=await f.bridge.approvalHook(event,{agentId:'developpement'});
  assert.match(hook.requireApproval.title,/Souleiman/);
  hook.requireApproval.onResolution('allow-once');
  assert.deepEqual(await new Bridge(f.options).approve('dev-call',event.params),{approvedOnce:true});
  await assert.rejects(f.bridge.approve('dev-call',event.params),/humaine/);
});

test('legacy Asia tasks keep ownership and unsupported agents never get a tool', async t => {
  const f=fixture(t);
  const task=await f.bridge.mutate({action:'start',requestId:'legacy-task',prompt:'test'});
  const state=f.bridge.load();delete state.tasks[task.taskId].agentId;f.bridge.save(state);
  assert.equal(f.bridge.own(task.taskId).sessionId,'ses_test0001');
  assert.throws(()=>new Bridge({...f.options,agentId:'developpement'}).own(task.taskId),/autre agent/);
  const factories=[],hooks=[];
  plugin.register({registerTool:factory=>factories.push(factory),on:(name,fn)=>hooks.push(fn)});
  for(const factory of factories){
    assert.ok(factory({agentId:'developpement'}));
    for(const agentId of ['recherche','formation-developpement','../asia'])assert.equal(factory({agentId}),null);
  }
  assert.equal((await hooks[0]({toolName:'asia_opencode_approve'},{agentId:'recherche'})).block,true);
});
