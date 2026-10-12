import {createHash,randomUUID} from 'node:crypto';
export const hash=s=>createHash('sha256').update(s).digest('hex');
export const canonical=v=>JSON.stringify((function sort(x){return Array.isArray(x)?x.map(sort):x&&typeof x==='object'?Object.fromEntries(Object.keys(x).sort().map(k=>[k,sort(x[k])])):x;})(v));
export const terminal=new Set(['published','cancelled','denied','expired','blocked']);
export class Problem extends Error {constructor(message,kind='blocked'){super(message);this.kind=kind;}}
export function validate(input,allowedRepos){
  if(!input||!allowedRepos.includes(input.repo))throw new Problem('Depot non autorise');
  if(!/^[A-Za-z0-9_-]{8,100}$/.test(input.requestId||''))throw new Problem('requestId stable de 8 a 100 caracteres requis');
  if(!input.title?.trim()||input.title.length>180||!input.body?.trim()||input.body.length>16000)throw new Problem('Titre et description invalides');
  if(!Array.isArray(input.files)||input.files.length<1||input.files.length>10)throw new Problem('De 1 a 10 documents requis');
  const files=input.files.map(f=>{
    if(!/^docs\/(?:[A-Za-z0-9_-]+\/)*[A-Za-z0-9_-]+\.md$/.test(f.path||''))throw new Problem('Seuls les documents Markdown sous docs/ sont permis');
    if(typeof f.content!=='string'||!f.content.trim()||Buffer.byteLength(f.content)>256*1024||f.content.includes('\0')||f.content.includes('\ufffd'))throw new Problem('Document UTF-8 invalide ou superieur a 256 Kio');
    return {path:f.path,content:f.content,hash:hash(f.content)};
  }).sort((a,b)=>a.path.localeCompare(b.path));
  if(new Set(files.map(f=>f.path)).size!==files.length||files.reduce((n,f)=>n+Buffer.byteLength(f.content),0)>1024*1024)throw new Problem('Chemins dupliques ou ensemble superieur a 1 Mio');
  return {repo:input.repo,requestId:input.requestId,title:input.title.trim(),body:input.body,files};
}
export function newJob(input,base){
  const id=randomUUID(),date=new Date().toISOString().replace(/\.\d{3}Z$/,'Z');
  const spec={...input,base:'main',baseSha:base.sha,baseTree:base.tree,date};
  const digest=hash(canonical(spec));
  return {id,spec,digest,head:'asia/publication-'+id,state:'awaiting_approval',progress:{},cancelRequested:false,
    expiresAt:new Date(Date.now()+86400000).toISOString()};
}
export function publicJob(j){return {id:j.id,repo:j.spec.repo,title:j.spec.title,head:j.head,base:j.spec.base,baseSha:j.spec.baseSha,
  digest:j.digest,state:j.state,files:j.spec.files.map(({path,hash})=>({path,hash})),expiresAt:j.expiresAt,
  url:j.progress.pr?.html_url,commit:j.progress.commit,error:j.error||null,cancelRequested:j.cancelRequested};}
export function review(j){return `# Publication ${j.id}\n\n${j.spec.title}\n\nDepot : ${j.spec.repo}\nBase : ${j.spec.baseSha}\nEmpreinte : ${j.digest}\n\n${j.spec.body}\n\n`+
  j.spec.files.map(f=>`---\n## ${f.path}\n\nSHA-256 : ${f.hash}\n\n${f.content}\n`).join('\n');}
// All external mutations are bounded operations. No shell, merge, force-push or deletion.
export async function advance(j,io){
  if(terminal.has(j.state)||j.state==='awaiting_approval')return;
  const gh=io.github;
  const checkpoint=async patch=>{Object.assign(j.progress,patch);await io.save(j);};
  const before=async()=>{
    if(await io.cancelled(j.id))throw new Problem('Annulation demandee','cancelled');
    if((await gh.base(j.spec.repo,j.spec.base)).sha!==j.spec.baseSha)throw new Problem('La branche de base a change. Preparer une nouvelle publication.');
  };
  try{
    if(j.approval?.digest!==j.digest||hash(canonical(j.spec))!==j.digest)throw new Problem('Autorisation ou contenu incoherent');
    if(await io.cancelled(j.id))throw new Problem('Annulation demandee','cancelled');
    // Resolve a previous uncertain PR call BEFORE attempting any other mutation.
    if(j.progress.prAttempted&&!j.progress.pr){
      const found=await gh.findPr(j);
      if(!found)throw new Problem('Creation de PR incertaine : aucune repetition automatique.','uncertain');
      await checkpoint({pr:found});
    }
    if(!j.progress.tree){await before();await checkpoint({stage:'tree'});await checkpoint({tree:await gh.tree(j)});}
    if(!j.progress.commit){await before();await checkpoint({stage:'commit'});await checkpoint({commit:await gh.commit(j)});}
    if(!j.progress.branch){
      await before();await checkpoint({stage:'branch'});
      const current=await gh.ref(j.spec.repo,j.head);
      if(current&&current!==j.progress.commit)throw new Problem('Branche existante avec un autre commit');
      if(!current)await gh.createRef(j);
      if(await gh.ref(j.spec.repo,j.head)!==j.progress.commit)throw new Problem('Branche non verifiee','uncertain');
      await checkpoint({branch:true});
    }
    if(!j.progress.pr){
      await before();const found=await gh.findPr(j);
      if(found)await checkpoint({pr:found});
      else{
        await checkpoint({stage:'pr',prAttempted:true}); // Durable intent before a non-idempotent call.
        await checkpoint({pr:await gh.createPr(j)});
      }
    }
    await gh.verify(j);
    j.state=await io.cancelled(j.id)?'cancelled':'published';
    j.error=j.state==='cancelled'?'Annulation recue pendant la publication ; PR conservee, non fusionnee.':null;
    await checkpoint({stage:'verified'});await io.notify(j);
  }catch(e){
    if(e.kind==='cancelled'){
      // Cancellation stops future writes; already-created remote effects are retained.
      try{const p=await gh.findPr(j);if(p)await checkpoint({pr:p});}catch{}
    }
    j.state=e.kind||'uncertain';j.error=e.message;
    await io.save(j);await io.notify(j);
  }
}
