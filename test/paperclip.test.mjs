import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {assertCreate,issueSession,Tickets} from '../infra/paperclip/plugin/tickets.mjs';
const company='11111111-1111-4111-8111-111111111111',project='22222222-2222-4222-8222-222222222222',
  agent='33333333-3333-4333-8333-333333333333',issue='44444444-4444-4444-8444-444444444444',run='55555555-5555-4555-8555-555555555555';
const normal={agentId:'asia',sessionKey:'agent:asia:telegram:direct:owner'};
const ticket={agentId:'asia',sessionKey:`agent:asia:paperclip:issue:${issue}`};
test('Paperclip: ordinary chat is not a ticket; specialists cannot create work',()=>{
  assert.throws(()=>assertCreate(normal,{ownerRequest:'Que penses-tu de cette idee ?'}),/Pas de ticket/);
  assert.throws(()=>assertCreate(normal,{ownerRequest:'Ne cree pas de ticket'}),/Pas de ticket/);
  assert.doesNotThrow(()=>assertCreate(normal,{ownerRequest:'Crée une tâche pour comparer les solutions'}));
  assert.throws(()=>assertCreate({...normal,agentId:'recherche'},{ownerRequest:'Cree un ticket'}),/reservees/);
  assert.throws(()=>assertCreate(ticket,{parentId:project}),/sous-tache/);
  assert.doesNotThrow(()=>assertCreate(ticket,{parentId:issue}));
  assert.throws(()=>issueSession({...ticket,agentId:'recherche'}),/invalide/);
});
function fixture(t,handler){
  const directory=fs.mkdtempSync(path.join(os.tmpdir(),'asia-paperclip-test-'));
  t.after(()=>fs.rmSync(directory,{recursive:true,force:true}));
  const calls=[];
  const cfg={enabled:true,apiUrl:'http://paperclip:3100',publicUrl:'https://example.invalid',companyId:company,projectId:project,
    ownerId:'owner',agents:{asia:{id:agent,token:'test-only'}}};
  const client=new Tickets({directory,credentials:()=>cfg,fetchImpl:async(url,options)=>{
    calls.push({route:url.pathname,options});const value=await handler(url,options);
    return {ok:true,status:200,json:async()=>value};
  }});
  return {client,calls,cfg};
}
const item={id:issue,identifier:'TEST-1',companyId:company,projectId:project,assigneeAgentId:agent,executionRunId:run};
test('Paperclip: latest comments are retained even when API returns newest first',async t=>{
  const comments=Array.from({length:35},(_,i)=>({id:String(i),body:String(i),createdAt:new Date(1700000000000+i*1000).toISOString()})).reverse();
  const {client}=fixture(t,url=>url.pathname.endsWith('/comments')?comments:item);
  const result=await client.call(normal,{action:'get',issueId:issue});
  assert.equal(result.comments.length,30);assert.equal(result.comments[0].id,'5');
  assert.equal(result.comments.at(-1).id,'34');
});
test('Paperclip: creation is attributed, reviewed by owner and replayed once',async t=>{
  const {client,calls}=fixture(t,()=>item);
  const params={action:'create',requestId:'create-test-1',ownerRequest:'Cree un ticket',title:'Etude',description:'Comparer les options'};
  const first=await client.call(normal,params);const second=await client.call(normal,params);
  assert.deepEqual(second,first);assert.equal(calls.length,1);
  const body=JSON.parse(calls[0].options.body);
  assert.equal(body.projectId,project);assert.equal(body.assigneeAgentId,agent);
  assert.equal(body.executionPolicy.stages[0].participants[0].userId,'owner');
  await assert.rejects(client.call(normal,{...params,title:'Different'}),/parametres differents/);
});
test('Paperclip: uncertain mutations are never silently retried',async t=>{
  const {client,calls}=fixture(t,()=>{throw Error('Connection lost');});
  const params={action:'create',requestId:'uncertain-test',ownerRequest:'Cree un ticket',title:'Etude',description:'Comparer'};
  await assert.rejects(client.call(normal,params),/Connection lost/);
  await assert.rejects(client.call(normal,params),/incertain/);assert.equal(calls.length,1);
});
test('Paperclip: cross-project reads, wrong runs and autonomous closure are denied',async t=>{
  const outside=fixture(t,()=>({...item,projectId:company}));
  await assert.rejects(outside.client.call(normal,{action:'get',issueId:issue}),/hors du projet/);
  const wrong=fixture(t,url=>url.pathname.includes('heartbeat-runs')?{agentId:company,status:'running'}:item);
  await assert.rejects(wrong.client.call(ticket,{action:'update',issueId:issue,runId:run,requestId:'wrong-run-1',status:'in_review',body:'Resultat'}),/differente/);
  const otherIssue=fixture(t,url=>url.pathname.includes('heartbeat-runs')?{agentId:agent,status:'running',contextSnapshot:{issueId:project}}:item);
  await assert.rejects(otherIssue.client.call(ticket,{action:'update',issueId:issue,runId:run,requestId:'other-issue-1',status:'in_review',body:'Resultat'}),/differente/);
  const current=fixture(t,url=>url.pathname.includes('heartbeat-runs')?{agentId:agent,status:'running',contextSnapshot:{issueId:issue}}:item);
  await assert.rejects(current.client.call(ticket,{action:'update',issueId:issue,runId:run,requestId:'close-test-1',status:'done',body:'Resultat'}),/cloture/);
  assert.equal(current.calls.filter(c=>c.options.method!=='GET').length,0);
});
