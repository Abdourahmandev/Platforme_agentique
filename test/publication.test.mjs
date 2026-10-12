import test from 'node:test';import assert from 'node:assert/strict';
import fs from 'node:fs/promises';import os from 'node:os';import path from 'node:path';
import {validate,newJob,advance,hash} from '../infra/publication/core.mjs';
import {command,snapshot} from '../infra/publication/plugin/client.mjs';
const input=()=>validate({repo:'owner/repo',requestId:'publication-001',title:'Documentation',body:'Approved scope',files:[{path:'docs/example.md',content:'# Bonjour\n'+('A'.repeat(24000))}]},['owner/repo']);
function harness(){
 const j=newJob(input(),{sha:'base',tree:'oldtree'});j.state='queued';j.approval={digest:j.digest};
 const calls=[],remote={};let saved=structuredClone(j),cancel=false;
 const github={base:async()=>({sha:'base'}),tree:async()=>{calls.push('tree');return 'tree';},commit:async()=>{calls.push('commit');return 'commit';},
  ref:async()=>remote.ref||null,createRef:async()=>{calls.push('branch');remote.ref='commit';},
  findPr:async()=>remote.pr||null,createPr:async()=>{calls.push('pr');remote.pr={number:7,html_url:'https://github.com/owner/repo/pull/7'};return remote.pr;},verify:async()=>{calls.push('verify');}};
 const io={github,save:async x=>{saved=structuredClone(x);},cancelled:async()=>cancel,notify:async()=>{calls.push('notify');}};
 return {j,io,calls,remote,get saved(){return saved;},cancel(){cancel=true;}};
}
test('documents larger than the old prompt limit remain intact and scope is bounded',()=>{
 const p=input();assert.equal(p.files[0].content.length,24010);assert.equal(p.files[0].hash,hash(p.files[0].content));
 for(const target of ['../secret','docs/../secret.md','.github/workflows/ci.md','docs/file.ps1'])assert.throws(()=>validate({...p,files:[{path:target,content:'x'}]},['owner/repo']));
 assert.throws(()=>validate(p,[]));assert.throws(()=>validate({...p,files:[...p.files,...p.files]},['owner/repo']));
});
test('publication finishes with verified remote result, then replay performs no writes',async()=>{
 const h=harness();await advance(h.j,h.io);assert.equal(h.saved.state,'published');assert.equal(h.saved.progress.pr.number,7);
 const before=h.calls.slice();await advance(h.saved,h.io);assert.deepEqual(h.calls,before);
});
test('JSONB key reordering does not invalidate an approved immutable manifest',async()=>{
 const h=harness();h.j.spec=Object.fromEntries(Object.entries(h.j.spec).reverse());await advance(h.j,h.io);assert.equal(h.saved.state,'published');
});
test('approval wait and cancellation perform no external writes',async()=>{
 for(const state of ['awaiting_approval','denied','cancelled','expired','blocked']){const h=harness();h.j.state=state;await advance(h.j,h.io);assert.deepEqual(h.calls,[]);}
 const h=harness();h.cancel();await advance(h.j,h.io);assert.equal(h.saved.state,'cancelled');assert.deepEqual(h.calls,['notify']);
});
test('lost PR response is reconciled after restart without a second creation',async()=>{
 const h=harness();const original=h.io.github.createPr;h.io.github.createPr=async j=>{await original(j);throw Error('connection lost');};
 await advance(h.j,h.io);assert.equal(h.saved.state,'uncertain');assert.equal(h.saved.progress.prAttempted,true);
 const resumed=structuredClone(h.saved);resumed.state='queued';await advance(resumed,h.io);
 assert.equal(h.saved.state,'published');assert.equal(h.calls.filter(x=>x==='pr').length,1);
});
test('uncertain PR absent remotely is never blindly retried',async()=>{
 const h=harness();h.io.github.createPr=async()=>{h.calls.push('pr');throw Error('lost');};await advance(h.j,h.io);
 const resumed=h.saved;resumed.state='queued';await advance(resumed,h.io);assert.equal(h.saved.state,'uncertain');assert.equal(h.calls.filter(x=>x==='pr').length,1);
});
test('lost branch response recovers the existing ref instead of creating again',async()=>{
 const h=harness();const create=h.io.github.createRef;h.io.github.createRef=async j=>{await create(j);throw Error('lost');};await advance(h.j,h.io);
 const resumed=h.saved;resumed.state='queued';await advance(resumed,h.io);assert.equal(h.saved.state,'published');assert.equal(h.calls.filter(x=>x==='branch').length,1);
});
test('changed base and foreign existing branch stop publication',async()=>{
 const h=harness();h.io.github.base=async()=>({sha:'someone-else'});await advance(h.j,h.io);assert.equal(h.saved.state,'blocked');assert.deepEqual(h.calls,['notify']);
 const b=harness();b.remote.ref='foreign';await advance(b.j,b.io);assert.equal(b.saved.state,'blocked');assert(!b.calls.includes('branch'));assert(!b.calls.includes('pr'));
});
test('cancellation after branch creation prevents PR and preserves remote branch',async()=>{
 const h=harness();const old=h.io.github.createRef;h.io.github.createRef=async j=>{await old(j);h.cancel();};await advance(h.j,h.io);
 assert.equal(h.saved.state,'cancelled');assert.equal(h.remote.ref,'commit');assert(!h.calls.includes('pr'));
});
test('verification failure cannot be reported as publication success',async()=>{
 const h=harness();h.io.github.verify=async()=>{throw Error('content mismatch');};await advance(h.j,h.io);assert.notEqual(h.saved.state,'published');assert.equal(h.saved.progress.pr.number,7);
});
test('only authenticated owner Telegram command can make a decision',async()=>{
 const cfg={ownerId:'123',ownerToken:'owner-token'};let calls=0;
 const call=async(c,t,r,b)=>{calls++;assert.equal(t,'owner-token');assert.equal(b.actor,'123');return {id:'job',title:'Doc',state:'queued',digest:'abcd0123456789'};};
 const good={channel:'telegram',accountId:'asia',isAuthorizedSender:true,senderId:'123',args:'approuver job abcd01234567'};
 for(const patch of [{channel:'webchat'},{senderId:'456'},{isAuthorizedSender:false},{accountId:'developpement'}])await command({...good,...patch},cfg,call);
 assert.equal(calls,0);const r=await command(good,cfg,call);assert.equal(calls,1);assert.match(r.text,/queued/);
});
test('artifact snapshot is scoped to the agents own project folder',async()=>{
 const dir=await fs.mkdtemp(path.join(os.tmpdir(),'publication-'));
 try{await fs.mkdir(path.join(dir,'asia','projets'),{recursive:true});await fs.writeFile(path.join(dir,'asia','projets','document.md'),'é'.repeat(15000));
  const f=await snapshot('asia',[{source:'document.md',path:'docs/document.md'}],dir);assert.equal(f[0].content,'é'.repeat(15000));
  await assert.rejects(snapshot('asia',[{source:'../secret',path:'docs/x.md'}],dir));await assert.rejects(snapshot('recherche',[],dir));
 }finally{assert(path.resolve(dir).startsWith(path.resolve(os.tmpdir())+path.sep+'publication-'));await fs.rm(dir,{recursive:true,force:true});}
});
