// Read-only protocol probe for an isolated cycle. Pairing remains an explicit
// operator CLI action; no token or device credential is printed.
import fs from 'node:fs';
import path from 'node:path';
import {GatewayClient,loadDevice} from '../gateway-client.mjs';
const cycle=process.env.ASIA_TRAINING_CYCLE||'';
if(!/^cycle-[1-9][0-9]{0,3}$/.test(cycle))throw Error('Named cycle required');
const root=path.join(process.env.LOCALAPPDATA,'AsiaDocker','training','cycles',cycle);
const s=JSON.parse(fs.readFileSync(path.join(root,'connection.json'),'utf8'));
const client=new GatewayClient({url:s.url,token:s.gateway_token,device:loadDevice(path.join(root,'gateway-test-device.json'))});
try{
  const hello=await client.connect();
  const result=await client.request('agents.list');
  const ids=result.agents.map(a=>a.id).sort();
  if(ids.join(',')!=='formation-asia,formation-developpement')throw Error('Unexpected roster');
  const report={protocol:hello.protocol,agents:ids};
  fs.writeFileSync(path.join(root,'probe.json'),JSON.stringify(report));
  console.log(JSON.stringify(report));
}catch(e){
  if(e.details?.requestId)fs.writeFileSync(path.join(root,'pairing-request.json'),JSON.stringify({requestId:e.details.requestId}));
  console.log(JSON.stringify({error:e.code||e.name,message:e.message.replaceAll(s.gateway_token,'[REDACTED]'),pairingRequired:!!e.details?.requestId}));
  process.exitCode=1;
}finally{client.close();}
