import {test} from 'node:test';
import assert from 'node:assert/strict';
import {submissionIdentity,clearSubmission} from '../src/submission.js';
test('submission identity survives retry/reload without storing message content',async()=>{
 const data=new Map();const store={getItem:k=>data.get(k),setItem:(k,v)=>data.set(k,v),removeItem:k=>data.delete(k)};
 const body={text:'PRIVATE TEST TEXT',attachments:[]};
 const first=await submissionIdentity('ses_a',body,store);
 assert.equal(await submissionIdentity('ses_a',JSON.parse(JSON.stringify(body)),store),first);
 assert(!JSON.stringify([...data.values()]).includes(body.text));
 assert.notEqual(await submissionIdentity('ses_b',body,store),first);
 assert.notEqual(await submissionIdentity('ses_a',{text:'Changed'},store),first);
 clearSubmission('ses_a',store);assert(!data.has('asia.pending.ses_a'));
});
