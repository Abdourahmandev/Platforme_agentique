import fs from 'node:fs';
import {Queue} from './queue.mjs';
import {mutationError} from './mutation-policy.mjs';
const root='/home/node/.openclaw/training-control';
const queue=new Queue(root);
export default {id:'asia-training',name:'Formation isolee',register(api){
  api.registerTool(context=>!['formation-developpement','formation-asia'].includes(context.agentId)?null:{
    name:'training_run',label:'Tests isoles',description:'Executer les tests Node/Python ou la compilation de repo/ dans un conteneur isole. Conserver jobId; status suit le resultat, cancel arrete la commande. Aucun shell libre.',
    parameters:{type:'object',additionalProperties:false,required:['action'],properties:{
      action:{type:'string',enum:['start','status','cancel']},operation:{type:'string',enum:['node_tests','python_tests','build']},jobId:{type:'string'}}},
    async execute(callId,params){try{const v=await queue.call(context,callId,params);return {content:[{type:'text',text:JSON.stringify(v)}],details:v};}
      catch(e){return {isError:true,content:[{type:'text',text:e.message}]};}}
  },{name:'training_run',optional:true});
  api.on('before_tool_call',(event,context)=>{
    if(!context.agentId?.startsWith('formation-'))return;
    try{
      const control=JSON.parse(fs.readFileSync(root+'/control.json','utf8'));
      if(!control.active)throw Error('Formation suspendue');
      const deniedMutation=mutationError(event,context);
      if(deniedMutation)throw Error(deniedMutation);
      if(event.toolName==='training_run'&&context.agentId!=='formation-developpement')throw Error('Execution reservee au specialiste');
      if(event.toolName?.startsWith('tavily__')){
        if(context.agentId!=='formation-recherche')throw Error('Recherche reservee au specialiste');
        if(!['tavily__tavily_search','tavily__tavily_extract'].includes(event.toolName))throw Error('Connecteur non autorise');
        if(event.params?.auto_parameters===true)throw Error('Parametres automatiques non autorises en formation');
        if(event.params?.search_depth&&event.params.search_depth!=='basic')throw Error('Utiliser search_depth basic');
        if(event.params?.extract_depth&&event.params.extract_depth!=='basic')throw Error('Utiliser extract_depth basic');
        if(event.params?.urls?.length>3)throw Error('Trois URL maximum');
        // Atomic slots across plugin instances; never rewrite the operator's stop flag.
        let slot=false;
        for(let i=0;i<20;i++){
          try{fs.writeFileSync(root+'/tavily-slot-'+i,'',{flag:'wx',mode:0o600});slot=true;break;}
          catch(e){if(e.code!=='EEXIST')throw e;}
        }
        if(!slot)throw Error('Quota de formation atteint');
      }
    }catch(e){return {block:true,blockReason:e.message};}
  });
}};
