// Minimal protocol v4 client for the future application contract, pinned to
// OpenClaw 2026.10.1. Never automatically replays an uncertain mutation.
import fs from 'node:fs';
import path from 'node:path';
import {createHash, generateKeyPairSync, randomUUID, sign} from 'node:crypto';
import {classifyTask} from './task-outcome.mjs';

function uncertainOutcomeError(message) {
  return Object.assign(new Error(message),{outcome:classifyTask({transportLost:true})});
}

export function loadDevice(filename) {
  if (fs.existsSync(filename)) return JSON.parse(fs.readFileSync(filename, 'utf8'));
  const {publicKey, privateKey} = generateKeyPairSync('ed25519');
  const raw = publicKey.export({type:'spki',format:'der'}).subarray(-32);
  const device = {id:createHash('sha256').update(raw).digest('hex'), publicKey:raw.toString('base64url'),
    privateKey:privateKey.export({type:'pkcs8',format:'pem'})};
  fs.mkdirSync(path.dirname(filename), {recursive:true});
  fs.writeFileSync(filename, JSON.stringify(device), {mode:0o600,flag:'wx'});
  return device;
}

export class GatewayClient {
  constructor({url, token, device, caps = [], scopes = ['operator.read','operator.write','operator.approvals','operator.questions']}) {
    if (!/^ws:\/\/(127\.0\.0\.1|localhost):\d+\/?$/.test(url) && !url.startsWith('wss://')) {
      throw new Error('Gateway credentials require loopback or TLS');
    }
    Object.assign(this,{url,token,device,scopes,caps});
    this.pending = new Map(); this.listeners = new Set();
  }
  async connect() {
    if(this.socket && [WebSocket.OPEN,WebSocket.CONNECTING].includes(this.socket.readyState))throw new Error('Already connected or connecting');
    const socket = new WebSocket(this.url);
    const pending = new Map();
    this.socket = socket; this.pending = pending;
    return new Promise((resolve,reject) => {
      const timeout = setTimeout(()=>{socket.close();reject(new Error('Handshake timeout'));},20000);
      const fail = error => {clearTimeout(timeout); reject(error);};
      socket.addEventListener('error',()=>fail(new Error('Gateway transport error')));
      socket.addEventListener('close',()=>{
        fail(new Error('Gateway connection closed'));
        for (const value of pending.values()) {clearTimeout(value.timeout);value.reject(uncertainOutcomeError('Connection lost; outcome unknown'));}
        pending.clear();
      });
      socket.addEventListener('message', async event => {
        if(this.socket!==socket)return;
        let frame; try {frame=JSON.parse(event.data);} catch {return;}
        if (frame.type==='res') {
          const entry=pending.get(frame.id); if(!entry)return;
          pending.delete(frame.id);clearTimeout(entry.timeout);
          if (frame.ok) entry.resolve(frame.payload);
          else {const error=new Error(frame.error?.message || 'Gateway request failed');error.details=frame.error?.details;error.code=frame.error?.code;entry.reject(error);}
        } else if (frame.event==='connect.challenge') {
          const {nonce,ts}=frame.payload;
          if(!Number.isSafeInteger(ts)||ts<0||typeof nonce!=='string')return fail(new Error('Invalid challenge'));
          const payload=['v3',this.device.id,'cli','cli','operator',this.scopes.join(','),String(ts),this.token,nonce,'win32',''].join('|');
          const signature=sign(null,Buffer.from(payload),this.device.privateKey).toString('base64url');
          try {
            const hello=await this.request('connect',{
              minProtocol:4,maxProtocol:4,client:{id:'cli',version:'asia-migration-1',platform:'win32',mode:'cli'},
              role:'operator',scopes:this.scopes,caps:this.caps,auth:{token:this.token},locale:'fr-FR',
              device:{id:this.device.id,publicKey:this.device.publicKey,signature,signedAt:ts,nonce},
            });
            clearTimeout(timeout);resolve(hello);
          } catch(error){fail(error);socket.close();}
        } else if(frame.type==='event') for(const listener of this.listeners)listener(frame);
      });
    });
  }
  request(method,params={},timeoutMs=30000) {
    const id=randomUUID();
    return new Promise((resolve,reject)=>{
      const timeout=setTimeout(()=>{this.pending.delete(id);reject(uncertainOutcomeError(`${method}: timeout; outcome unknown`));},timeoutMs);
      this.pending.set(id,{resolve,reject,timeout});
      try {this.socket.send(JSON.stringify({type:'req',id,method,params}));}
      catch{clearTimeout(timeout);this.pending.delete(id);reject(uncertainOutcomeError(`${method}: transport error; outcome unknown`));}
    });
  }
  onEvent(listener){this.listeners.add(listener);return ()=>this.listeners.delete(listener);}
  close(){this.socket?.close();}
}
