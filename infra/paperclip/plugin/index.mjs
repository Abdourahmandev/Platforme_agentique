import fs from 'node:fs';
import {Tickets} from './tickets.mjs';
import {notionCall} from './notion.mjs';
const root='/home/node/.openclaw/paperclip-control';
const tickets=new Tickets({directory:root+'/receipts',credentials:()=>JSON.parse(fs.readFileSync(root+'/credentials.json','utf8'))});
const string={type:'string'};
export default {id:'asia-paperclip',name:'Tickets des agents',register(api){
  api.registerTool(context=>!['asia','developpement','recherche'].includes(context.agentId)?null:{
    name:'asia_ticket',label:'Tickets Paperclip',
    description:'Lire les tickets des projets partages et leurs discussions. Asia cree des tickets seulement sur demande explicite du proprietaire, ou des sous-taches depuis un ticket. Une conversation normale ne cree aucun ticket. Les agents publient commentaires et resultats; la cloture reste humaine. Dans un projet avec relectrice (voir projectDirectory), un ticket de developpement passe d abord par sa revue puis par l approbation du proprietaire. costs : cout reel en dollars d un projet et de chacun de ses tickets. Aucun acces aux conversations privees des autres agents.',
    parameters:{type:'object',additionalProperties:false,required:['action'],properties:{
      action:{type:'string',enum:['list','get','costs','create','checkout','comment','update']},issueId:string,
      requestId:{type:'string',description:'Identifiant stable de mutation, 8 a 100 caracteres; conserver en cas de resultat incertain.'},
      runId:{type:'string',description:'PAPERCLIP_RUN_ID du reveil courant, requis pour les mutations depuis un ticket.'},
      title:string,description:string,assignee:{type:'string',enum:['asia','developpement','recherche','maryam'],description:'Identifiant stable, jamais le nom affiche : Souleiman = developpement, Saredo = recherche, Asia = asia, Maryam = maryam. Voir agentDirectory dans list/get.'},parentId:string,
      project:{type:'string',description:'Projet (voir projectDirectory dans list/get). Absent : projet partage par defaut. Une sous-tache reste dans le projet de son parent.'},
      ownerRequest:{type:'string',description:'Citation exacte de la demande explicite de creation du proprietaire (ou de sa reponse "je valide" a ta proposition), pour un nouveau ticket depuis une conversation.'},
      proposal:{type:'string',description:'Si ownerRequest est une simple validation : citation exacte de ta proposition de creation a laquelle le proprietaire repond.'},
      body:string,status:{type:'string',enum:['in_progress','blocked','in_review'],description:'in_progress : travail en cours (ex. ticket parent qui suit ses lots) ; blocked : vrai blocage seulement.'}}},
    async execute(callId,params){try{const value=await tickets.call(context,params);return {content:[{type:'text',text:JSON.stringify(value)}],details:value};}
      catch(error){return {isError:true,content:[{type:'text',text:error.message}]};}}
  },{name:'asia_ticket',optional:true});
  api.registerTool(context=>context.agentId!=='asia'?null:{
    name:'asia_notion',label:'Projets Decidata (Notion)',
    description:'Documenter les projets Decidata dans la base Notion "Projets Decidata" (seul acces Notion de la plateforme). list : fiches existantes. create : nouvelle fiche (fields.name obligatoire). update : modifier les champs d une fiche. add_section : ajouter une section (title + text ; paragraphes separes par une ligne vide, listes avec "- "). Champs : name, status (Estimation, En cours, Termine, En pause, Abandonne), repo (URL https), start, end (AAAA-MM-JJ), lots, estimateCost, realCost (dollars US), estimateDays, realDays (jours), summary. Aucune donnee personnelle ni secret.',
    parameters:{type:'object',additionalProperties:false,required:['action'],properties:{
      action:{type:'string',enum:['list','setup','create','update','add_section']},
      projectId:{type:'string',description:'Identifiant de la fiche (champ id de list ou create), pour update et add_section.'},
      fields:{type:'object',description:'Champs de la fiche pour create et update.'},
      title:{type:'string',description:'Titre de la section, pour add_section.'},
      text:{type:'string',description:'Contenu de la section, pour add_section.'}}},
    async execute(callId,params){try{const config=JSON.parse(fs.readFileSync(root+'/credentials.json','utf8')).notion;
      const value=await notionCall(config,params);return {content:[{type:'text',text:JSON.stringify(value)}],details:value};}
      catch(error){return {isError:true,content:[{type:'text',text:error.message}]};}}
  },{name:'asia_notion',optional:true});
}};
