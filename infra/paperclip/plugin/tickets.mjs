import fs from 'node:fs';
import path from 'node:path';
import {createHash} from 'node:crypto';

const UUID=/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i;
const AGENTS=['asia','developpement','recherche'];
export function issueSession(context){
  const match=String(context.sessionKey||'').match(/^agent:([^:]+):paperclip:issue:([a-f0-9-]+)$/i);
  if(!match)return null;
  if(match[1]!==context.agentId || !UUID.test(match[2]))throw Error('Session de ticket invalide');
  return match[2];
}
// Projects the tool may touch: the historical shared project plus optional named
// projects ({slug:{id,name,reviewer,reviewFor}}). A project with a reviewer adds a
// review stage by that agent before the owner's approval, for tickets assigned to reviewFor.
export function projectsOf(cfg){
  return {[cfg.defaultProject||'plateforme']:{id:cfg.projectId,name:cfg.projectName||'Plateforme agentique'},...(cfg.projects||{})};
}
export function resolveProject(cfg,slug){
  const projects=projectsOf(cfg);
  if(!slug)return {slug:cfg.defaultProject||'plateforme',...projects[cfg.defaultProject||'plateforme']};
  if(!projects[slug])throw Error('Projet inconnu: '+slug+'. Projets: '+Object.keys(projects).join(', '));
  return {slug,...projects[slug]};
}
export function executionPolicyFor(cfg,project,assignee){
  const stages=[];
  if(project.reviewer&&cfg.agents[project.reviewer]&&assignee===project.reviewFor&&assignee!==project.reviewer)
    stages.push({type:'review',participants:[{type:'agent',agentId:cfg.agents[project.reviewer].id}]});
  stages.push({type:'approval',participants:[{type:'user',userId:cfg.ownerId}]});
  return {mode:'normal',stages};
}
export function assertCreate(context,params,assignees=AGENTS){
  if(context.agentId!=='asia')throw Error('La creation et la delegation de tickets sont reservees a Asia');
  const session=issueSession(context);
  if(session){
    if(params.parentId!==session)throw Error('Une delegation doit etre une sous-tache du ticket courant');
  }else{
    if(params.parentId)throw Error('Creer les sous-taches depuis le ticket parent');
    const text=String(params.ownerRequest||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'');
    if(/\b(?:ne|pas|jamais|sans|don't|not|never)\b/i.test(text) ||
      !/(?:cree|creer|creez|ouvre|ouvrir|ajoute|ajouter|create|open|add)\b[\s\S]{0,100}\b(?:tache|ticket|task|issue)\b/i.test(text))
      throw Error('Pas de ticket automatique. Demander une instruction explicite de creation de tache, puis citer cette demande dans ownerRequest.');
  }
  if(!assignees.includes(params.assignee||'asia'))throw Error('Responsable inconnu');
}
const publicIssue=(item,url)=>Object.fromEntries(Object.entries({id:item.id,identifier:item.identifier,title:item.title,
  description:item.description,status:item.status,assigneeAgentId:item.assigneeAgentId,assigneeUserId:item.assigneeUserId,
  awaitingHumanReview:item.status==='in_review'&&Boolean(item.assigneeUserId),
  returnAgentId:item.executionState?.returnAssignee?.agentId??null,parentId:item.parentId,
  projectId:item.projectId,url:`${url}/issues/${item.identifier||item.id}`}).filter(([,v])=>v!==undefined));

export class Tickets {
  constructor({directory,credentials,fetchImpl=fetch}){Object.assign(this,{directory,credentials,fetchImpl});}
  async call(context,params){
    if(!AGENTS.includes(context.agentId))throw Error('Agent non autorise');
    const cfg=this.credentials(),actor=cfg.agents[context.agentId];
    if(!cfg.enabled||!actor)throw Error('Integration Paperclip suspendue');
    const agentDirectory=Object.entries(cfg.agents).map(([agentId,v])=>({agentId,paperclipId:v.id,name:v.name||agentId}));
    const projects=projectsOf(cfg),projectIds=Object.values(projects).map(p=>p.id);
    const projectDirectory=Object.entries(projects).map(([project,v])=>({project,name:v.name||project,
      reviewer:v.reviewer||null,reviewFor:v.reviewFor||null}));
    const base=new URL(cfg.apiUrl);
    if(base.origin!=='http://paperclip:3100')throw Error('Destination Paperclip invalide');
    const request=async(method,route,body,runId)=>{
      const response=await this.fetchImpl(new URL('/api'+route,base),{method,
        headers:{Authorization:`Bearer ${actor.token}`,'Content-Type':'application/json',...(runId?{'X-Paperclip-Run-Id':runId}:{})},
        ...(body===undefined?{}:{body:JSON.stringify(body)}),signal:AbortSignal.timeout(20000),redirect:'error'});
      if(!response.ok)throw Error(`Paperclip HTTP ${response.status}. Ne pas repeter une mutation incertaine.`);
      return response.status===204?null:await response.json();
    };
    const get=async(id)=>{
      if(!UUID.test(id||''))throw Error('Utiliser l UUID du ticket');
      const item=await request('GET','/issues/'+id);
      if(item.companyId!==cfg.companyId||!projectIds.includes(item.projectId))throw Error('Ticket hors du projet partage');
      return item;
    };
    if(params.action==='list'){
      const project=resolveProject(cfg,params.project);
      const rows=await request('GET',`/companies/${cfg.companyId}/issues?projectId=${project.id}&limit=50`);
      return {tickets:rows.filter(i=>i.projectId===project.id).slice(0,50).map(i=>publicIssue(i,cfg.publicUrl)),agentDirectory,projectDirectory};
    }
    if(params.action==='get'){
      const item=await get(params.issueId);
      const comments=await request('GET',`/issues/${item.id}/comments`);
      return {ticket:publicIssue(item,cfg.publicUrl),comments:[...comments].sort((a,b)=>String(a.createdAt).localeCompare(String(b.createdAt))).slice(-30).map(c=>({id:c.id,authorAgentId:c.authorAgentId,
        authorUserId:c.authorUserId,body:c.body,createdAt:c.createdAt})),agents:Object.fromEntries(Object.entries(cfg.agents).map(([k,v])=>[k,v.id])),agentDirectory,projectDirectory};
    }
    if(params.action==='costs'){
      // Real dollars per ticket, attributed from LiteLLM by infra/paperclip/sync-costs.py (finished runs only).
      const project=resolveProject(cfg,params.project);
      const rows=(await request('GET',`/companies/${cfg.companyId}/issues?projectId=${project.id}&limit=100`)).filter(i=>i.projectId===project.id);
      const tickets=[];
      for(const i of rows){const c=await request('GET',`/issues/${i.id}/cost-summary`);
        if(c.costCents>0)tickets.push({identifier:i.identifier,title:i.title,status:i.status,dollars:c.costCents/100,runs:c.runCount});}
      const total=tickets.reduce((sum,t)=>sum+t.dollars,0);
      return {project:project.name||params.project,totalDollars:Math.round(total*100)/100,tickets,
        note:'Couts reels LiteLLM des executions terminees (mis a jour toutes les 15 minutes) ; hors conversations Telegram.'};
    }
    if(!['create','checkout','comment','update'].includes(params.action))throw Error('Action inconnue');
    if(!/^[a-zA-Z0-9_-]{8,100}$/.test(params.requestId||''))throw Error('requestId stable de 8 a 100 caracteres requis');
    if(!context.sessionKey)throw Error('Session requise pour les mutations');
    const session=issueSession(context);
    let item,runId;
    if(params.action==='create')assertCreate(context,params,Object.keys(cfg.agents));
    else item=await get(params.issueId);
    if(session){
      const own=await get(session);
      if(own.assigneeAgentId!==actor.id)throw Error('Le ticket courant appartient a un autre agent');
      if(!UUID.test(params.runId||''))throw Error('runId du reveil Paperclip requis');
      const run=await request('GET','/heartbeat-runs/'+params.runId);
      if(run.agentId!==actor.id || run.status!=='running' || run.contextSnapshot?.issueId!==session ||
        (own.executionRunId&&own.executionRunId!==params.runId))
        throw Error('Execution Paperclip inactive ou differente');
      runId=params.runId;
    }else if(params.action!=='create'&&params.action!=='comment')throw Error('Mettre a jour un ticket depuis son execution Paperclip');
    if(['checkout','update'].includes(params.action) && (item.id!==session||item.assigneeAgentId!==actor.id))
      throw Error('Modification reservee au responsable du ticket courant');
    if(params.action==='update'&&!['blocked','in_review'].includes(params.status))
      throw Error('Seuls blocked et in_review sont autorises; la cloture est reservee au proprietaire');
    if(['comment','update'].includes(params.action)&&(!params.body?.trim()||params.body.length>16000))throw Error('Commentaire de 1 a 16000 caracteres requis');
    if(params.action==='create'){
      if(!params.title?.trim()||params.title.length>200||!params.description?.trim()||params.description.length>16000)throw Error('Titre et description requis, tailles maximales 200 et 16000');
      if(params.parentId){
        // A subtask lives in its parent's project; an explicit different project is refused.
        const parent=await get(params.parentId);
        const inherited=Object.entries(projects).find(([,p])=>p.id===parent.projectId)?.[0];
        if(params.project&&params.project!==inherited)throw Error('Une sous-tache reste dans le projet de son parent');
        params={...params,project:inherited};
      }
      resolveProject(cfg,params.project);
    }
    const key=createHash('sha256').update(`${context.agentId}|${context.sessionKey}|${params.requestId}`).digest('hex');
    const hash=createHash('sha256').update(JSON.stringify(params)).digest('hex');
    fs.mkdirSync(this.directory,{recursive:true,mode:0o700});
    const file=path.join(this.directory,key+'.json');
    try{fs.writeFileSync(file,JSON.stringify({hash,state:'pending',action:params.action}),{flag:'wx',mode:0o600});}
    catch(error){
      if(error.code!=='EEXIST')throw error;
      const old=JSON.parse(fs.readFileSync(file,'utf8'));
      if(old.hash!==hash)throw Error('requestId reutilise avec des parametres differents');
      if(old.state==='complete')return old.result;
      throw Error('Resultat incertain: verifier le ticket, ne pas soumettre a nouveau');
    }
    let value;
    if(params.action==='create'){
      const project=resolveProject(cfg,params.project),assignee=params.assignee||'asia';
      value=publicIssue(await request('POST',`/companies/${cfg.companyId}/issues`,{
        title:params.title,description:params.description,status:'todo',priority:'medium',projectId:project.id,
        assigneeAgentId:cfg.agents[assignee].id,parentId:params.parentId||null,idempotencyKey:'asia-'+key,
        executionPolicy:executionPolicyFor(cfg,project,assignee),
      },runId),cfg.publicUrl);
    }else if(params.action==='checkout'){
      value=publicIssue(await request('POST',`/issues/${item.id}/checkout`,{agentId:actor.id,
        expectedStatuses:['todo','backlog','blocked','in_review']},runId),cfg.publicUrl);
    }else if(params.action==='comment'){
      const comment=await request('POST',`/issues/${item.id}/comments`,{body:params.body},runId);
      value={id:comment.id,issueId:item.id,posted:true,
        notice:'Commentaire enregistre; cela ne confirme pas une relance. Relire le ticket. Si in_review et attribue a un humain, une decision de demande de modifications est necessaire pour le rendre a l agent.'};
    }else{
      value=publicIssue(await request('PATCH',`/issues/${item.id}`,{status:params.status,comment:params.body},runId),cfg.publicUrl);
    }
    const tmp=file+'.tmp';fs.writeFileSync(tmp,JSON.stringify({hash,state:'complete',result:value}),{mode:0o600});fs.renameSync(tmp,file);
    return value;
  }
}
