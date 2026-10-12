import fs from 'node:fs';
import http from 'node:http';
import {timingSafeEqual} from 'node:crypto';
import {Store} from './store.mjs';
import {Github} from './github.mjs';
import {Problem,validate,publicJob,review,advance,hash} from './core.mjs';
const cfg=JSON.parse(fs.readFileSync(process.env.PUBLICATION_CONFIG||'/run/private/config.json'));
const store=new Store(cfg.databaseUrl),github=new Github(cfg.githubToken);
await store.init();
// A crashed delivery may already have reached Telegram; never blindly resend it.
await store.pool.query("UPDATE outbox SET state='uncertain' WHERE state='sending'");
const same=(a,b)=>typeof a==='string'&&typeof b==='string'&&a.length===b.length&&timingSafeEqual(Buffer.from(a),Buffer.from(b));
const server=http.createServer(async(req,res)=>{
  const reply=(status,data)=>{res.writeHead(status,{'Content-Type':'application/json','Cache-Control':'no-store'});res.end(JSON.stringify(data));};
  try{
    if(req.url==='/health'&&req.method==='GET'){await store.pool.query('SELECT 1');return reply(200,{ok:true});}
    const token=(req.headers.authorization||'').replace(/^Bearer /,'');
    const owner=same(token,cfg.ownerToken),actor=Object.keys(cfg.agentTokens).find(a=>same(token,cfg.agentTokens[a]));
    if(!owner&&!actor)return reply(401,{error:'Authentification requise'});
    const match=req.url.match(/^\/jobs\/([a-f0-9-]{36})(?:\/(decision|review))?$/);
    if(req.method==='GET'&&match){const j=await store.get(match[1]);return reply(200,match[2]==='review'?{review:review(j)}:publicJob(j));}
    if(req.method!=='POST')return reply(404,{error:'Route inconnue'});
    let chunks=[],size=0;for await(const chunk of req){size+=chunk.length;if(size>1500000)throw new Problem('Requete superieure a 1,5 Mo');chunks.push(chunk);}
    const body=JSON.parse(Buffer.concat(chunks).toString('utf8'));
    if(req.url==='/jobs'){
      const input=validate(body,cfg.allowedRepos);const existing=await store.existing(actor||'operator',input);if(existing)return reply(200,publicJob(existing));
      const base=await github.base(input.repo,'main');
      for(const f of input.files){const old=await github.request('GET',`/repos/${input.repo}/contents/${f.path}?ref=${base.sha}`,undefined,true);if(old?.encoding==='base64'&&hash(Buffer.from(old.content,'base64'))===f.hash)throw new Problem('Fichier inchange a retirer de la demande : '+f.path);}
      return reply(201,publicJob(await store.create(actor||'operator',input,base)));
    }
    if(match?.[2]==='decision'){
      if(!owner)return reply(403,{error:'Decision humaine requise'});
      if(body.actor!==cfg.ownerId&&body.actor!=='operator-authorized')throw new Problem('Proprietaire inconnu');
      return reply(200,publicJob(await store.decide(match[1],body.digest,body.action,body.actor)));
    }
    reply(404,{error:'Route inconnue'});
  }catch(e){reply(e instanceof Problem?409:500,{error:e instanceof Problem?e.message:'Erreur interne ; consulter le statut avant repetition'});}
});
server.listen(18820,'0.0.0.0');
let stopped=false;
async function deliver(n){
  const j=await store.get(n.job_id);const base='https://api.telegram.org/bot'+cfg.telegramToken+'/';
  let method='sendMessage',body,headers;
  if(n.kind==='review'){
    const form=new FormData();form.set('chat_id',cfg.ownerId);form.set('caption','Contenu complet a publier — '+j.id);form.set('document',new Blob([review(j)],{type:'text/markdown'}),'publication-'+j.id+'.md');body=form;
  }else{
    const short=j.digest.slice(0,12);
    const pending=n.kind==='awaiting_approval';
    const text=pending?`Publication prete : ${j.spec.title}\nDepot : ${j.spec.repo}\n${j.spec.files.map(f=>f.path).join('\n')}\n\nApres revue du document, envoie cette commande dans le bot Asia :\n/publication approuver ${j.id} ${short}\n\nPour refuser :\n/publication refuser ${j.id} ${short}\n\nLa demande reste disponible 24 h, independamment de la conversation.`:
      `Publication ${j.id}\nEtat : ${n.kind}\n${j.progress.pr?.html_url||j.error||'Etat enregistre.'}\n/publication voir ${j.id}`;
    body=JSON.stringify({chat_id:cfg.ownerId,text});headers={'Content-Type':'application/json'};
  }
  if(n.kind==='review')method='sendDocument';
  const r=await fetch(base+method,{method:'POST',headers,body,signal:AbortSignal.timeout(20000)});const value=await r.json();if(!r.ok||!value.ok)throw Error('Notification non confirmee');
  await store.notificationDone(n.id,value.result.message_id);
}
async function work(){while(!stopped){try{for(const {id} of await store.pending()){if(stopped)break;await store.locked(id,(j,io)=>advance(j,{...io,github}));}}catch{console.error('Publication worker: iteration interrupted; durable state retained.');}await new Promise(r=>setTimeout(r,3000));}}
async function notifications(){while(!stopped){try{const n=await store.nextNotification();if(n){try{await deliver(n);}catch{await store.notificationUncertain(n.id);console.error('Publication notification uncertain; no automatic duplicate.');}}}catch{console.error('Publication notifications unavailable.');}await new Promise(r=>setTimeout(r,3000));}}
if(cfg.workerEnabled!==false)work();
if(cfg.notificationsEnabled!==false)notifications();
for(const signal of ['SIGTERM','SIGINT'])process.on(signal,()=>{stopped=true;server.close();setTimeout(()=>process.exit(0),25000).unref();});
