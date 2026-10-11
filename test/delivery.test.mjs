import {test} from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {once} from 'node:events';
import {mkdtemp,writeFile,rm} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {createApp} from '../server.mjs';

async function fixture(t){
 const dir=await mkdtemp(path.join(os.tmpdir(),'asia-delivery-test-'));const secretPath=path.join(dir,'secret.json');
 await writeFile(secretPath,JSON.stringify({username:'test',password:'not-a-real-secret'}));
 const state={calls:0,mode:'success',messages:new Map(),busy:false,delay:0};
 const mock=http.createServer(async(req,res)=>{
  let raw='';for await(const chunk of req)raw+=chunk;
  const p=new URL(req.url,'http://test').pathname;res.setHeader('Content-Type','application/json');
  const send=(v,status=200)=>{res.writeHead(status);res.end(JSON.stringify(v));};
  if(p.endsWith('/prompt_async')){
   state.calls++;const data=JSON.parse(raw);
   if(state.delay)await new Promise(r=>setTimeout(r,state.delay));
   if(state.mode==='reject')return send({error:'invalid'},400);
   if(state.mode!=='lost-before')state.messages.set(data.messageID,{info:{id:data.messageID,role:'user'},parts:data.parts});
   if(state.mode.startsWith('lost')){res.destroy();return;}
   res.writeHead(204);res.end();return;
  }
  if(p==='/global/health')return send({healthy:true});
  if(p==='/session/status')return send(state.busy?{ses_test:{type:'busy'}}:{});
  if(p.includes('/message/'))return state.messages.has(p.split('/').pop())?send(state.messages.get(p.split('/').pop())):send({error:'not found'},404);
  return send({id:'ses_test',directory:'C:/test',metadata:{asiaProfile:'auto'}});
 });mock.listen(0,'127.0.0.1');await once(mock,'listening');
 const config={port:0,upstream:`http://127.0.0.1:${mock.address().port}`,secretPath,requestDBPath:path.join(dir,'requests.sqlite'),directory:'C:/test',publicHost:'example.test',ownerLogin:'test',defaultProfile:'auto',profiles:[{id:'auto',providerID:'test',modelID:'test'}]};
 let app,base,csrf;
 async function start(){app=createApp(config);app.listen(0,'127.0.0.1');await once(app,'listening');config.port=app.address().port;base=`http://127.0.0.1:${config.port}`;csrf=(await(await fetch(base+'/api/bootstrap')).json()).csrf;}
 async function stop(){app.closeAllConnections();app.close();await once(app,'close');}
 await start();
 t.after(async()=>{await stop();mock.closeAllConnections();mock.close();await once(mock,'close');assert(path.resolve(dir).startsWith(path.resolve(os.tmpdir())+path.sep));await rm(dir,{recursive:true,force:true});});
 const post=async(route,data,token=csrf)=>{const r=await fetch(base+route,{method:'POST',headers:{Origin:base,'X-Asia-CSRF':token,'Content-Type':'application/json'},body:JSON.stringify(data)});return {status:r.status,data:await r.json()};};
 return {state,post,prompt:(id,text='Test request')=>post('/api/sessions/ses_test/prompt',{requestId:id,text}),restart:async()=>{await stop();await start();},token:()=>csrf};
}
test('repeated and concurrent IDs submit once; a changed payload is rejected',async t=>{
 const f=await fixture(t);f.state.delay=80;const id=randomUUID();
 const results=await Promise.all([f.prompt(id),f.prompt(id)]);assert.equal(f.state.calls,1);assert(results.some(r=>r.status===200));
 const replay=await f.prompt(id);assert.equal(replay.status,200);assert.equal(f.state.calls,1);
 assert.equal((await f.prompt(id,'Changed')).status,409);assert.equal(f.state.calls,1);
 await f.restart();assert.equal((await f.prompt(id)).status,200);assert.equal(f.state.calls,1);
});
test('lost acknowledgement is reconciled across an application restart',async t=>{
 const f=await fixture(t);f.state.mode='lost-after';const id=randomUUID();assert.equal((await f.prompt(id)).status,503);
 await f.restart();const retry=await f.prompt(id);assert.equal(retry.status,200);assert.equal(retry.data.reconciled,true);assert.equal(f.state.calls,1);
});
test('uncertain delivery is never replayed; explicit abandonment unlocks the session',async t=>{
 const f=await fixture(t);f.state.mode='lost-before';const id=randomUUID();assert.equal((await f.prompt(id)).status,503);
 assert.equal((await f.prompt(id)).data.code,'request_uncertain');assert.equal((await f.prompt(randomUUID())).status,409);assert.equal(f.state.calls,1);
 const route=`/api/sessions/ses_test/submissions/${id}/abandon`;
 assert.equal((await f.post(route,{})).status,400);
 assert.equal((await f.post(route,{acknowledgePossibleDelivery:true})).status,200);
 assert.equal((await f.prompt(id)).data.code,'request_abandoned');assert.equal(f.state.calls,1);
 f.state.mode='success';assert.equal((await f.prompt(randomUUID())).status,200);assert.equal(f.state.calls,2);
});
test('busy session and simultaneous different requests are blocked at the server',async t=>{
 const f=await fixture(t);f.state.busy=true;assert.equal((await f.prompt(randomUUID())).data.code,'session_busy');assert.equal(f.state.calls,0);
 f.state.busy=false;f.state.delay=80;const r=await Promise.all([f.prompt(randomUUID()),f.prompt(randomUUID())]);assert.equal(f.state.calls,1);assert(r.some(x=>x.status===409));
});
test('definitive rejection is remembered and stale CSRF never submits',async t=>{
 const f=await fixture(t);f.state.mode='reject';const id=randomUUID();assert.equal((await f.prompt(id)).status,400);assert.equal((await f.prompt(id)).status,400);assert.equal(f.state.calls,1);
 const old=f.token();await f.restart();assert.equal((await f.post('/api/sessions/ses_test/prompt',{requestId:randomUUID(),text:'No send'},old)).data.code,'csrf_invalid');assert.equal(f.state.calls,1);
 assert.equal((await f.post('/api/sessions/ses_test/prompt',{text:'Missing ID'})).status,400);
});
