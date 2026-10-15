import test from 'node:test';
import assert from 'node:assert/strict';
import {notionCall} from '../infra/paperclip/plugin/notion.mjs';

const config={url:'http://notion-bridge:8080/',key:'k'};
function fake(status,body,seen){return async(url,init)=>{seen.push({url,init});return {ok:status<400,status,json:async()=>body};};}

test('notion: routes each action to the bridge with its key',async()=>{
  const seen=[];
  await notionCall(config,{action:'create',fields:{name:'Messagerie'}},fake(201,{id:'x'},seen));
  await notionCall(config,{action:'add_section',projectId:'a'.repeat(32),title:'Bilan',text:'ok'},fake(200,{ok:true},seen));
  assert.equal(seen[0].url,'http://notion-bridge:8080/projects');
  assert.equal(seen[0].init.method,'POST');
  assert.deepEqual(JSON.parse(seen[0].init.body),{fields:{name:'Messagerie'}});
  assert.equal(seen[0].init.headers.Authorization,'Bearer k');
  assert.equal(seen[1].url,'http://notion-bridge:8080/projects/'+'a'.repeat(32)+'/sections');
});

test('notion: refuses missing config, unknown actions and missing projectId',async()=>{
  await assert.rejects(notionCall(undefined,{action:'list'}),/pas configure/);
  await assert.rejects(notionCall(config,{action:'delete'}),/inconnue/);
  await assert.rejects(notionCall(config,{action:'update',fields:{}}),/projectId/);
});

test('notion: surfaces bridge errors',async()=>{
  await assert.rejects(notionCall(config,{action:'list'},fake(503,{error:'Cle Notion absente'},[])),/Cle Notion absente/);
});
