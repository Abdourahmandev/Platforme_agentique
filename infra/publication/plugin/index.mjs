import fs from 'node:fs';
import {snapshot,request,command} from './client.mjs';
const credentials=()=>JSON.parse(fs.readFileSync('/home/node/.openclaw/publication-control/credentials.json','utf8'));
export default {id:'asia-publication',name:'Publication documentaire durable',register(api){
  api.registerTool(context=>!['asia','developpement'].includes(context.agentId)?null:{
    name:'asia_publication',label:'Publication documentaire',
    description:'Preparer une publication documentaire persistante avec des fichiers du workspace, ou consulter son statut. Aucun accord humain ne peut etre donne par cet outil. La preparation envoie le contenu au proprietaire ; publication apres sa commande Telegram, independamment du modele. Ne pas utiliser OpenCode pour publier ces documents.',
    parameters:{type:'object',additionalProperties:false,required:['action'],properties:{
      action:{type:'string',enum:['prepare','status']},id:{type:'string'},requestId:{type:'string',minLength:8,maxLength:100},
      repo:{type:'string'},title:{type:'string',maxLength:180},body:{type:'string',maxLength:16000},
      files:{type:'array',minItems:1,maxItems:10,items:{type:'object',required:['source','path'],additionalProperties:false,properties:{source:{type:'string',description:'Chemin relatif a projets/ dans TON workspace, 256 Kio maximum par fichier.'},path:{type:'string',description:'Chemin Markdown cible sous docs/ dans le depot.'}}}}
    }},
    async execute(callId,p){try{const cfg=credentials();let value;
      if(p.action==='status')value=await request(cfg,cfg.agentTokens[context.agentId],'/jobs/'+p.id);
      else if(p.action==='prepare')value=await request(cfg,cfg.agentTokens[context.agentId],'/jobs',{requestId:p.requestId,repo:p.repo,title:p.title,body:p.body,files:await snapshot(context.agentId,p.files)});
      else throw Error('Action invalide');
      return {content:[{type:'text',text:JSON.stringify(value)}],details:value};
    }catch(e){return {isError:true,content:[{type:'text',text:e.message+' ; conserver requestId et consulter le statut avant repetition.'}]};}}
  },{name:'asia_publication',optional:true});
  api.registerCommand({name:'publication',description:'Voir ou valider une publication persistante',acceptsArgs:true,requireAuth:true,handler:ctx=>command(ctx,credentials())});
}};
