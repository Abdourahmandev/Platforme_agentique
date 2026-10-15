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
test('Paperclip: display names resolve to existing IDs without exposing credentials',async t=>{
  const {client,cfg}=fixture(t,url=>url.pathname.endsWith('/comments')?[]:
    url.pathname.includes('/companies/')?[item]:item);
  cfg.agents.developpement={id:project,name:'Souleiman',token:'private-dev'};
  cfg.agents.recherche={id:company,name:'Saredo',token:'private-research'};
  for(const params of [{action:'get',issueId:issue},{action:'list'}]){
    const result=await client.call(normal,params);
    assert.deepEqual(result.agentDirectory.find(a=>a.name==='Souleiman'),{agentId:'developpement',paperclipId:project,name:'Souleiman'});
    assert.deepEqual(result.agentDirectory.find(a=>a.name==='Saredo'),{agentId:'recherche',paperclipId:company,name:'Saredo'});
    assert.ok(!JSON.stringify(result).includes('private-dev'));
    assert.ok(!JSON.stringify(result).includes('private-research'));
  }
  assert.throws(()=>assertCreate(normal,{ownerRequest:'Cree un ticket',assignee:'Souleiman'}),/Responsable inconnu/);
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
test('Paperclip: human review is visible and a comment does not promise a restart',async t=>{
  const pending={...item,status:'in_review',assigneeAgentId:null,assigneeUserId:'owner',
    executionState:{returnAssignee:{type:'agent',agentId:agent},internalField:'private-state'}};
  const {client,calls}=fixture(t,(url,options)=>url.pathname.endsWith('/comments')?
    (options.method==='POST'?{id:'comment-1'}:[]):pending);
  const result=await client.call(normal,{action:'get',issueId:issue});
  assert.equal(result.ticket.assigneeUserId,'owner');assert.equal(result.ticket.awaitingHumanReview,true);
  assert.equal(result.ticket.returnAgentId,agent);assert.equal(result.ticket.executionState,undefined);
  const posted=await client.call(normal,{action:'comment',issueId:issue,requestId:'review-comment-1',body:'Merci de corriger les sources'});
  assert.equal(posted.posted,true);assert.match(posted.notice,/ne confirme pas une relance/);
  assert.equal(calls.filter(c=>c.options.method!=='GET').length,1);
  assert.equal(calls.at(-1).route,`/api/issues/${issue}/comments`);
  for(const active of [{...item,status:'in_review',assigneeUserId:null},{...pending,status:'done'}]){
    const {client:reader}=fixture(t,url=>url.pathname.endsWith('/comments')?[]:active);
    assert.equal((await reader.call(normal,{action:'get',issueId:issue})).ticket.awaitingHumanReview,false);
  }
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
const usine='66666666-6666-4666-8666-666666666666',maryam='77777777-7777-4777-8777-777777777777',dev='88888888-8888-4888-8888-888888888888';
function factory(t,handler){
  const f=fixture(t,handler);
  f.cfg.agents.developpement={id:dev,name:'Souleiman',token:'private-dev'};
  f.cfg.agents.maryam={id:maryam,name:'Maryam'};
  f.cfg.projects={usine:{id:usine,name:'Usine test',reviewer:'maryam',reviewFor:'developpement'}};
  return f;
}
test('Paperclip: factory development tickets get QA review before owner approval',async t=>{
  const {client,calls}=factory(t,()=>({...item,projectId:usine}));
  await client.call(normal,{action:'create',requestId:'usine-dev-1',ownerRequest:'Cree une tache pour la fonction somme',
    title:'Fonction somme',description:'Implementer et tester',assignee:'developpement',project:'usine'});
  const body=JSON.parse(calls.at(-1).options.body);
  assert.equal(body.projectId,usine);assert.equal(body.assigneeAgentId,dev);
  assert.deepEqual(body.executionPolicy.stages.map(s=>s.type),['review','approval']);
  assert.equal(body.executionPolicy.stages[0].participants[0].agentId,maryam);
  assert.equal(body.executionPolicy.stages[1].participants[0].userId,'owner');
});
test('Paperclip: non-development or default-project tickets keep owner approval only',async t=>{
  const {client,calls}=factory(t,()=>item);
  await client.call(normal,{action:'create',requestId:'usine-spec-1',ownerRequest:'Cree une tache de specification',
    title:'Spec',description:'Rediger la spec',assignee:'asia',project:'usine'});
  assert.deepEqual(JSON.parse(calls.at(-1).options.body).executionPolicy.stages.map(s=>s.type),['approval']);
  await client.call(normal,{action:'create',requestId:'default-dev-1',ownerRequest:'Cree une tache',
    title:'Etude',description:'Comparer',assignee:'developpement'});
  const body=JSON.parse(calls.at(-1).options.body);
  assert.equal(body.projectId,project);assert.deepEqual(body.executionPolicy.stages.map(s=>s.type),['approval']);
});
test('Paperclip: unknown projects are refused and subtasks stay in their parent project',async t=>{
  const {client,calls}=factory(t,(url,options)=>url.pathname.includes('heartbeat-runs')?
    {agentId:agent,status:'running',contextSnapshot:{issueId:issue}}:
    options.method==='GET'&&url.pathname.includes('/companies/')?[{...item,projectId:usine}]:{...item,projectId:usine});
  await assert.rejects(client.call(normal,{action:'create',requestId:'unknown-proj-1',ownerRequest:'Cree une tache',
    title:'X',description:'Y',project:'inconnu'}),/Projet inconnu/);
  await assert.rejects(client.call(ticket,{action:'create',requestId:'cross-proj-1',parentId:issue,runId:run,
    title:'X',description:'Y',assignee:'developpement',project:'plateforme'}),/projet de son parent/);
  await client.call(ticket,{action:'create',requestId:'sub-proj-1',parentId:issue,runId:run,
    title:'Developper',description:'Implementer',assignee:'developpement'});
  const body=JSON.parse(calls.filter(c=>c.options.method==='POST').at(-1).options.body);
  assert.equal(body.projectId,usine);assert.equal(body.executionPolicy.stages[0].type,'review');
  const listed=await client.call(normal,{action:'list',project:'usine'});
  assert.ok(listed.projectDirectory.some(p=>p.project==='usine'&&p.reviewer==='maryam'));
});
test('Paperclip: costs sums real dollars per ticket of the project',async t=>{
  const other={...item,id:'66666666-6666-4666-8666-666666666666',identifier:'TEST-2'};
  const {client}=fixture(t,url=>url.pathname.endsWith('/cost-summary')
    ?(url.pathname.includes(issue)?{costCents:102,runCount:4}:{costCents:0,runCount:1})
    :[item,other,{...item,id:'77777777-7777-4777-8777-777777777777',projectId:'other'}]);
  const result=await client.call(normal,{action:'costs'});
  assert.equal(result.totalDollars,1.02);
  assert.deepEqual(result.tickets.map(x=>x.identifier),['TEST-1']);
});
