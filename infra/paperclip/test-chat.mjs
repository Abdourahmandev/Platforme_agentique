// Explicit live test; one model request, private synthetic session, no Telegram delivery.
import fs from 'node:fs';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {GatewayClient,loadDevice} from '../gateway-client.mjs';
const root=path.join(process.env.LOCALAPPDATA,'AsiaDocker');
const cfg=JSON.parse(fs.readFileSync(path.join(root,'runtime-private.json'),'utf8'));
const client=new GatewayClient({url:'ws://127.0.0.1:18789',token:cfg.gateway_token,
  device:loadDevice(path.join(root,'gateway-test-device.json'))});
const creation=process.argv.includes('--create');
try{
  await client.connect();
  const sessionKey='agent:asia:paperclip-chat-test-'+randomUUID();
  const events=[];client.onEvent(e=>{if(e.event==='chat')events.push(e.payload);});
  const sent=await client.request('chat.send',{sessionKey,idempotencyKey:randomUUID(),
    message:creation?
      'Cree une tache nommee "Validation : conversation vers ticket" et confie-la a Recherche. Mission : expliquer en une phrase la difference entre une conversation et une tache suivie, puis publier le marqueur PAPERCLIP_CHAT_CREATION_OK dans le resultat en attente de ma validation. Donne-moi le numero et le lien du ticket.':
      'Bonjour Asia. A quoi sert Paperclip dans notre equipe ? Explique en deux phrases. Ceci est une conversation normale, ne cree aucune tache ni aucun ticket et ne contacte personne.'});
  const deadline=Date.now()+180000;
  while(Date.now()<deadline&&!events.some(e=>e.runId===sent.runId&&['final','error','aborted'].includes(e.state)))
    await new Promise(r=>setTimeout(r,500));
  const history=await client.request('chat.history',{sessionKey,limit:50});
  const passed=events.some(e=>e.runId===sent.runId&&e.state==='final');
  fs.writeFileSync(path.join(process.env.LOCALAPPDATA,'AsiaPaperclip',creation?'explicit-creation-private.json':'ordinary-chat-private.json'),JSON.stringify({sessionKey,passed,history},null,2));
  console.log(JSON.stringify({passed,sessionKey,verification:creation?'Verify one new task, its owner and its result.':'Compare ticket count before and after this test.'}));
  if(!passed)process.exitCode=1;
}finally{client.close();}
