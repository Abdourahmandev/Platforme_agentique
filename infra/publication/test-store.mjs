// Run inside the publisher container. Only the separately provisioned *_test database is used.
import fs from 'node:fs';import assert from 'node:assert/strict';import {randomUUID} from 'node:crypto';
import {Store} from './store.mjs';import {validate} from './core.mjs';
const cfg=JSON.parse(fs.readFileSync('/run/private/config.json'));const url=new URL(cfg.databaseUrl);url.pathname='/asia_publication_test';
assert(url.pathname.endsWith('_test'));let s=new Store(url.toString());await s.init();
const checks=[];const check=(name,condition)=>{assert(condition,name);checks.push(name);};
const input=()=>validate({repo:'test/repo',requestId:randomUUID(),title:'Test',body:'No external effects',files:[{path:'docs/test.md',content:'é'.repeat(20000)}]},['test/repo']);
const base={sha:'base',tree:'tree'};
try{
 const i=input();const jobs=await Promise.all(Array.from({length:5},()=>s.create('test',i,base)));
 check('concurrent submissions return same durable job',new Set(jobs.map(j=>j.id)).size===1);
 const j=jobs[0];check('one review and one approval notification',(await s.pool.query('SELECT count(*)::int AS n FROM outbox WHERE job_id=$1',[j.id])).rows[0].n===2);
 await assert.rejects(s.existing('test',{...i,title:'changed'}));checks.push('changed payload with same key rejected');
 await assert.rejects(s.decide(j.id,'wrong','approve','owner'));checks.push('wrong document hash rejected');
 await s.pool.end();s=new Store(url.toString());check('content survives process/store replacement',(await s.get(j.id)).spec.files[0].content===i.files[0].content);
 await s.decide(j.id,j.digest.slice(0,12),'approve','owner');
 check('approval is durable',(await s.get(j.id)).approval.digest===j.digest);
 let release;const gate=new Promise(r=>release=r);let started;const ready=new Promise(r=>started=r);let first=0,second=0;
 const a=s.locked(j.id,async()=>{first++;started();await gate;});await ready;
 const other=new Store(url.toString());await other.locked(j.id,async()=>{second++;});release();await a;await other.pool.end();
 check('two workers cannot execute the same job',first===1&&second===0);
 await s.decide(j.id,j.digest,'cancel','owner');check('cancellation remains set',(await s.get(j.id)).cancelRequested);
 await assert.rejects(s.decide(j.id,j.digest,'approve','owner'));checks.push('cancelled job cannot be approved');
 const denied=await s.create('test',input(),base);await s.decide(denied.id,denied.digest,'deny','owner');await assert.rejects(s.decide(denied.id,denied.digest,'approve','owner'));checks.push('denial is terminal');
 const expired=await s.create('test',input(),base);expired.expiresAt=new Date(Date.now()-1000).toISOString();await s.pool.query('UPDATE jobs SET job=$2 WHERE id=$1',[expired.id,expired]);
 check('late approval expires instead of authorizing',(await s.decide(expired.id,expired.digest,'approve','owner')).state==='expired');
 console.log(JSON.stringify({passed:true,checks}));
}finally{await s.pool.end();}
