import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {Queue,validate} from '../infra/training/plugin/queue.mjs';

test('training queue denies foreign agents, foreign sessions, unsupported commands and stale runner',async t=>{
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'asia-training-'));
  t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
  const write=(n,v)=>fs.writeFileSync(path.join(root,n),JSON.stringify(v));
  write('control.json',{active:true});write('heartbeat.json',{timestamp:0});
  const queue=new Queue(root),ctx={agentId:'formation-developpement',sessionKey:'agent:formation-developpement:test'};
  await assert.rejects(queue.call({agentId:'developpement'},'1',{action:'start',operation:'node_tests'}),/reserve/);
  assert.throws(()=>validate({action:'start',operation:'shell'}),/interdite/);
  assert.throws(()=>validate({action:'status',jobId:'../../credentials'}),/invalide/);
  await assert.rejects(queue.call(ctx,'1',{action:'start',operation:'node_tests'}),/indisponible/);
  const jobId='a'.repeat(32);write(jobId+'.request.json',{agentId:ctx.agentId,sessionKey:'other'});
  await assert.rejects(queue.call(ctx,'1',{action:'status',jobId}),/etrangere/);
  write('control.json',{active:false});
  await assert.rejects(queue.call(ctx,'1',{action:'start',operation:'node_tests'}),/suspendue/);
});

test('training queue deduplicates an identical call and rejects changed arguments',async t=>{
  const root=fs.mkdtempSync(path.join(os.tmpdir(),'asia-training-'));
  t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
  const queue=new Queue(root),ctx={agentId:'formation-developpement',sessionKey:'agent:formation-developpement:test'};
  fs.writeFileSync(path.join(root,'control.json'),JSON.stringify({active:true}));
  fs.writeFileSync(path.join(root,'heartbeat.json'),JSON.stringify({timestamp:Date.now()}));
  const jobId=createHash('sha256').update(ctx.sessionKey+'\0call').digest('hex').slice(0,32);
  fs.writeFileSync(path.join(root,jobId+'.result.json'),JSON.stringify({jobId,status:'passed',exitCode:0}));
  for(let i=0;i<2;i++)assert.equal((await queue.call(ctx,'call',{action:'start',operation:'node_tests'})).status,'passed');
  assert.equal(fs.readdirSync(root).filter(n=>n.endsWith('.request.json')).length,1);
  await assert.rejects(queue.call(ctx,'call',{action:'start',operation:'build'}),/modifiee/);
});
import {mutationError} from '../infra/training/plugin/mutation-policy.mjs';

test('training writes stay in the four reviewed candidate paths including patches',()=>{
  const ctx={agentId:'formation-developpement'};
  assert.equal(mutationError({toolName:'edit',params:{path:'repo/infra/task-outcome.mjs'}},ctx),undefined);
  assert.equal(mutationError({toolName:'write',params:{path:'/home/node/.openclaw/workspaces/formation-developpement/repo/test/health-report.test.mjs'}},ctx),undefined);
  for(const path of ['.openclaw/tmp/list.txt','AGENTS.md','repo/server.mjs','repo/../AGENTS.md','repo\\infra\\task-outcome.mjs'])assert.ok(mutationError({toolName:'write',params:{path}},ctx));
  assert.ok(mutationError({toolName:'apply_patch',params:{input:'*** Begin Patch\n*** Add File: .openclaw/tmp/list.txt\n+x\n*** End Patch'}},ctx));
  assert.ok(mutationError({toolName:'apply_patch',params:{input:'*** Delete File: repo/test/task-outcome.test.mjs'}},ctx));
  assert.equal(mutationError({toolName:'apply_patch',params:{input:'*** Begin Patch\n*** Update File: repo/infra/task-outcome.mjs\n@@\n-old\n+new\n*** End Patch'}},ctx),undefined);
  assert.equal(mutationError({toolName:'write',params:{path:'NOT_A_TRAINING_PATH'}},{agentId:'asia'}),undefined);
});
