import {Problem,hash} from './core.mjs';
export class Github{
  constructor(token,fetchImpl=fetch){this.token=token;this.fetch=fetchImpl;}
  async request(method,route,body,missing=false){
    let r;try{r=await this.fetch('https://api.github.com'+route,{method,redirect:'error',headers:{Authorization:'Bearer '+this.token,Accept:'application/vnd.github+json','Content-Type':'application/json','X-GitHub-Api-Version':'2022-11-28'},body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(20000)});}catch{throw new Problem('GitHub : reponse inconnue apres interruption','uncertain');}
    if(missing&&r.status===404)return null;
    if(!r.ok)throw new Problem('GitHub HTTP '+r.status,[429,500,502,503,504].includes(r.status)?'uncertain':'blocked');
    return r.status===204?null:r.json();
  }
  async ref(repo,head){return (await this.request('GET',`/repos/${repo}/git/ref/heads/${head}`,undefined,true))?.object?.sha||null;}
  async base(repo,branch){const sha=await this.ref(repo,branch);if(!sha)throw new Problem('Branche de base introuvable');const c=await this.request('GET',`/repos/${repo}/git/commits/${sha}`);return {sha,tree:c.tree.sha};}
  async tree(j){const r=await this.request('POST',`/repos/${j.spec.repo}/git/trees`,{base_tree:j.spec.baseTree,tree:j.spec.files.map(f=>({path:f.path,mode:'100644',type:'blob',content:f.content}))});if(r.sha===j.spec.baseTree)throw new Problem('Aucun changement a publier');return r.sha;}
  async commit(j){const identity={name:'Asia Publication',email:'publication@users.noreply.github.com',date:j.spec.date};return (await this.request('POST',`/repos/${j.spec.repo}/git/commits`,{message:j.spec.title+'\n\nPublication-ID: '+j.id+'\n',tree:j.progress.tree,parents:[j.spec.baseSha],author:identity,committer:identity})).sha;}
  async createRef(j){try{await this.request('POST',`/repos/${j.spec.repo}/git/refs`,{ref:'refs/heads/'+j.head,sha:j.progress.commit});}catch(e){if(await this.ref(j.spec.repo,j.head)!==j.progress.commit)throw e;}}
  async findPr(j){
    const owner=j.spec.repo.split('/')[0];
    const rows=await this.request('GET',`/repos/${j.spec.repo}/pulls?state=all&head=${encodeURIComponent(owner+':'+j.head)}&base=${encodeURIComponent(j.spec.base)}&per_page=100`);
    if(rows.length>1)throw new Problem('Plusieurs PR correspondent : inspection requise');
    if(!rows.length)return null;
    const p=rows[0];if(p.head.sha!==j.progress.commit||p.head.ref!==j.head||p.base.ref!==j.spec.base||p.head.repo?.full_name!==j.spec.repo)throw new Problem('PR existante differente du contenu attendu');
    return {number:p.number,html_url:p.html_url};
  }
  async createPr(j){try{const p=await this.request('POST',`/repos/${j.spec.repo}/pulls`,{title:j.spec.title,body:j.spec.body+`\n\n<!-- asia-publication:${j.id}:${j.digest} -->`,head:j.head,base:j.spec.base,draft:false,maintainer_can_modify:false});return {number:p.number,html_url:p.html_url};}catch(e){const found=await this.findPr(j);if(found)return found;throw new Problem(e.message+' ; creation a reconcilier','uncertain');}}
  async verify(j){
    const p=await this.request('GET',`/repos/${j.spec.repo}/pulls/${j.progress.pr.number}`);
    if(p.head.sha!==j.progress.commit||p.head.ref!==j.head||p.base.ref!==j.spec.base||p.base.sha!==j.spec.baseSha||p.merged||p.state!=='open')throw new Problem('Etat de PR different de la publication attendue');
    const files=await this.request('GET',`/repos/${j.spec.repo}/pulls/${p.number}/files?per_page=100`);
    if(files.length!==j.spec.files.length||files.some(f=>!j.spec.files.some(x=>x.path===f.filename)||!['added','modified'].includes(f.status)))throw new Problem('Portee des fichiers de PR inattendue');
    for(const f of j.spec.files){const b=await this.request('GET',`/repos/${j.spec.repo}/contents/${f.path}?ref=${j.progress.commit}`);if(b.encoding!=='base64'||hash(Buffer.from(b.content,'base64'))!==f.hash)throw new Problem('Contenu distant different : '+f.path);}
  }
}
