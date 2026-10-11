import fs from 'node:fs';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {GatewayClient,loadDevice} from './gateway-client.mjs';

const root=path.join(process.env.LOCALAPPDATA,'AsiaDocker');
const privateState=JSON.parse(fs.readFileSync(path.join(root,'runtime-private.json'),'utf8'));
const device=loadDevice(path.join(root,'gateway-test-device.json'));
const client=new GatewayClient({url:'ws://127.0.0.1:18789',token:privateState.gateway_token,device});
const checks={};
try {
  const hello=await client.connect();
  checks.handshake={passed:hello.protocol===4,protocol:hello.protocol,scopes:hello.auth.scopes};
  if(process.argv.includes('--discover'))console.log(hello.features.methods.filter(m=>/chat|approval|session.*sub/.test(m)));
  const agents=await client.request('agents.list');
  const ids=agents.agents.map(a=>a.id).sort();
  checks.agents_list={passed:JSON.stringify(ids)===JSON.stringify(['asia','developpement','recherche']),agents:ids};
  const sessions=await client.request('sessions.list',{limit:20});
  checks.sessions_list={passed:Array.isArray(sessions.sessions),count:sessions.sessions?.length};
  try {
    await client.request('config.set',{});
    checks.admin_denied={passed:false};
  } catch(error){checks.admin_denied={passed:/scope|unauthorized|forbidden/i.test(error.message)};}
  if(process.argv.includes('--inference')) {
    const key='agent:asia:migration-rpc-'+randomUUID();
    const id=randomUUID();const events=[];
    client.onEvent(event=>{if(event.event==='chat')events.push(event.payload);});
    const request={sessionKey:key,message:'Test technique. Reponds uniquement RPC_OK.',idempotencyKey:id};
    const first=await client.request('chat.send',request);
    const duplicate=await client.request('chat.send',request);
    checks.idempotency={passed:first.runId===duplicate.runId};
    const deadline=Date.now()+150000;
    while(Date.now()<deadline && !events.some(e=>e.runId===first.runId&&['final','error','aborted'].includes(e.state)))
      await new Promise(resolve=>setTimeout(resolve,500));
    checks.streaming={passed:events.some(e=>e.runId===first.runId&&e.state==='delta')};
    checks.response_final={passed:events.some(e=>e.runId===first.runId&&e.state==='final')};
    const history=await client.request('chat.history',{sessionKey:key,limit:20});
    checks.single_user_message={passed:history.messages.filter(m=>m.role==='user').length===1};
    client.close();
    await client.connect();
    const after=await client.request('chat.history',{sessionKey:key,limit:20});
    checks.reconnect_history={passed:after.messages.length===history.messages.length};
    const next=await client.request('chat.send',{sessionKey:key,message:'Ecris une longue histoire de mille mots.',idempotencyKey:randomUUID()});
    const stopped=await client.request('chat.abort',{sessionKey:key,runId:next.runId});
    checks.abort={passed:stopped.ok===true && stopped.aborted===true};
  }
  console.log(JSON.stringify(checks,null,2));
  fs.writeFileSync(path.join(root,'gateway-test-result.json'),JSON.stringify(checks,null,2));
  if(Object.values(checks).some(c=>!c.passed))process.exitCode=1;
} catch(error) {
  // Pairing request IDs are public identifiers; the keypair and tokens stay local.
  console.log(JSON.stringify({error:error.code || error.name,message:error.message,
    pairingRequestId:error.details?.requestId,detailsCode:error.details?.code}));
  if(error.details?.requestId)fs.writeFileSync(path.join(root,'gateway-pairing-request.txt'),error.details.requestId);
  process.exitCode=1;
} finally {client.close();}
