// Run inside Paperclip. Read operator credentials from stdin, never arguments.
import fs from 'node:fs';
import {createHash,createPublicKey,sign} from 'node:crypto';
const cfg=JSON.parse(fs.readFileSync(0,'utf8'));
const raw=createPublicKey(cfg.devicePrivateKeyPem).export({type:'spki',format:'der'}).subarray(-32);
const deviceId=createHash('sha256').update(raw).digest('hex');
const scopes=['operator.read','operator.write'];
const socket=new WebSocket(cfg.url);
const deadline=setTimeout(()=>{console.log(JSON.stringify({passed:false,error:'timeout'}));socket.close();process.exitCode=1;},20000);
socket.addEventListener('error',()=>{clearTimeout(deadline);console.log(JSON.stringify({passed:false,error:'transport'}));process.exitCode=1;});
socket.addEventListener('message',event=>{
  const f=JSON.parse(event.data);
  if(f.event==='connect.challenge'){
    const ts=Date.now(),nonce=f.payload.nonce;
    const payload=['v3',deviceId,'gateway-client','backend','operator',scopes.join(','),String(ts),cfg.authToken,nonce,process.platform,''].join('|');
    socket.send(JSON.stringify({type:'req',id:'connect',method:'connect',params:{minProtocol:4,maxProtocol:4,
      client:{id:'gateway-client',mode:'backend',version:'paperclip',platform:process.platform},role:'operator',scopes,
      auth:{token:cfg.authToken},device:{id:deviceId,publicKey:raw.toString('base64url'),signature:sign(null,Buffer.from(payload),cfg.devicePrivateKeyPem).toString('base64url'),signedAt:ts,nonce}}}));
  }else if(f.type==='res'&&f.id==='connect'){
    if(!f.ok){console.log(JSON.stringify({passed:false,code:f.error?.code,detail:f.error?.details?.code,requestId:f.error?.details?.requestId,deviceId}));process.exitCode=1;clearTimeout(deadline);socket.close();return;}
    if(f.payload.protocol!==4||JSON.stringify([...(f.payload.auth?.scopes||[])].sort())!==JSON.stringify([...scopes].sort()))process.exitCode=1;
    console.log(JSON.stringify({handshake:true,protocol:f.payload.protocol,scopes:f.payload.auth?.scopes,deviceId}));
    socket.send(JSON.stringify({type:'req',id:'admin-check',method:'config.set',params:{}}));
  }else if(f.type==='res'&&f.id==='admin-check'){
    const denied=!f.ok&&/scope|unauthorized|forbidden/i.test(f.error?.message||'');
    console.log(JSON.stringify({adminDenied:denied}));if(!denied)process.exitCode=1;
    clearTimeout(deadline);socket.close();
  }
});
