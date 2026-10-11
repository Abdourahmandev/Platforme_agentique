import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {Bridge, assertAsia} from '../infra/opencode-bridge/bridge.mjs';

function fixture(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(),'asia-bridge-'));
  t.after(() => fs.rmSync(dir, {recursive:true,force:true}));
  const calls = [], pending = [{id:'per_test0001',sessionID:'ses_test0001',permission:'bash',patterns:['echo synthetic']}];
  let failPrompt = false;
  const options = {stateFile:path.join(dir,'tasks.json'), credentials:() => ({username:'fixture',password:'fixture',directory:'C:/synthetic'}),
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
  assert.throws(() => assertAsia({agentId:'developpement'}));
  assert.throws(() => assertAsia({}));
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
