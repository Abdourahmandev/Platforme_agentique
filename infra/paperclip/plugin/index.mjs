import fs from 'node:fs';
import {Tickets} from './tickets.mjs';
const root='/home/node/.openclaw/paperclip-control';
const tickets=new Tickets({directory:root+'/receipts',credentials:()=>JSON.parse(fs.readFileSync(root+'/credentials.json','utf8'))});
const string={type:'string'};
export default {id:'asia-paperclip',name:'Tickets des agents',register(api){
  api.registerTool(context=>!['asia','developpement','recherche'].includes(context.agentId)?null:{
    name:'asia_ticket',label:'Tickets Paperclip',
    description:'Lire les tickets du projet partage et leurs discussions. Asia cree des tickets seulement sur demande explicite du proprietaire, ou des sous-taches depuis un ticket. Une conversation normale ne cree aucun ticket. Les agents publient commentaires et resultats; la cloture reste humaine. Aucun acces aux conversations privees des autres agents.',
    parameters:{type:'object',additionalProperties:false,required:['action'],properties:{
      action:{type:'string',enum:['list','get','create','checkout','comment','update']},issueId:string,
      requestId:{type:'string',description:'Identifiant stable de mutation, 8 a 100 caracteres; conserver en cas de resultat incertain.'},
      runId:{type:'string',description:'PAPERCLIP_RUN_ID du reveil courant, requis pour les mutations depuis un ticket.'},
      title:string,description:string,assignee:{type:'string',enum:['asia','developpement','recherche']},parentId:string,
      ownerRequest:{type:'string',description:'Citation exacte de la demande explicite de creation du proprietaire, pour un nouveau ticket depuis Telegram.'},
      body:string,status:{type:'string',enum:['blocked','in_review']}}},
    async execute(callId,params){try{const value=await tickets.call(context,params);return {content:[{type:'text',text:JSON.stringify(value)}],details:value};}
      catch(error){return {isError:true,content:[{type:'text',text:error.message}]};}}
  },{name:'asia_ticket',optional:true});
}};
