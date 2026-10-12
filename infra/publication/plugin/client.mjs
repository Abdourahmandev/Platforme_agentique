import fs from 'node:fs/promises';
import path from 'node:path';
export async function snapshot(agent,files,root='/home/node/.openclaw/workspaces'){
  if(!['asia','developpement'].includes(agent))throw Error('Agent non autorise');
  if(!Array.isArray(files)||files.length<1||files.length>10)throw Error('De 1 a 10 fichiers requis');
  const base=await fs.realpath(path.join(root,agent,'projets'));
  const result=[];
  for(const f of files){
    if(typeof f.source!=='string'||path.isAbsolute(f.source)||f.source.includes('..')||f.source.includes('\\'))throw Error('Source relative au dossier projets requise');
    const actual=await fs.realpath(path.join(base,f.source));
    if(!actual.startsWith(base+path.sep))throw Error('Source hors du workspace');
    const stat=await fs.stat(actual);if(!stat.isFile()||stat.size>256*1024)throw Error('Document absent ou superieur a 256 Kio');
    const bytes=await fs.readFile(actual);result.push({path:f.path,content:new TextDecoder('utf-8',{fatal:true}).decode(bytes)});
  }
  return result;
}
export async function request(cfg,token,route,body){
  if(cfg.url!=='http://publication:18820')throw Error('Service inattendu');
  const r=await fetch(cfg.url+route,{method:body===undefined?'GET':'POST',headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(60000)});
  const value=await r.json();if(!r.ok)throw Error(value.error||'Publication indisponible');return value;
}
export async function command(ctx,cfg,call=request){
  if(ctx.channel!=='telegram'||ctx.accountId!=='asia'||ctx.isAuthorizedSender!==true||String(ctx.senderId)!==String(cfg.ownerId))return {text:'Commande reservee au proprietaire dans le bot Asia.'};
  const [action,id,digest,...extra]=(ctx.args||'').trim().split(/\s+/);
  if(!['voir','approuver','refuser','annuler','verifier'].includes(action)||!id||extra.length)return {text:'/publication voir IDENTIFIANT\n/publication approuver IDENTIFIANT EMPREINTE\n/publication refuser IDENTIFIANT EMPREINTE\n/publication annuler IDENTIFIANT EMPREINTE\n/publication verifier IDENTIFIANT EMPREINTE'};
  try{
    const value=action==='voir'?await call(cfg,cfg.ownerToken,'/jobs/'+id):await call(cfg,cfg.ownerToken,'/jobs/'+id+'/decision',{action:{approuver:'approve',refuser:'deny',annuler:'cancel',verifier:'reconcile'}[action],digest,actor:String(ctx.senderId)});
    return {text:`Publication ${value.id}\n${value.title}\nEtat : ${value.state}${value.cancelRequested?' (annulation demandee)':''}\n${value.url||value.error||'Le service poursuit le suivi independamment de la conversation.'}\nEmpreinte : ${value.digest.slice(0,12)}`};
  }catch(e){return {text:'Publication : '+e.message+'. Ne pas recreer une demande dont le resultat est incertain.'};}
}
