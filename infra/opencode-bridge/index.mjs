import fs from 'node:fs';
import {Bridge, assertBridgeAgent, bridgeStateFile} from './bridge.mjs';

const base = '/home/node/.openclaw';
const bridges = new Map();
function bridgeFor(context) {
  const agentId = assertBridgeAgent(context);
  if (!bridges.has(agentId)) bridges.set(agentId, new Bridge({agentId, stateFile:bridgeStateFile(base, agentId),
    credentials:() => JSON.parse(fs.readFileSync(base + '/credentials/asia-opencode.json', 'utf8'))}));
  return bridges.get(agentId);
}
const string = {type:'string'};
const result = value => ({content:[{type:'text',text:JSON.stringify(value)}], details:value});
const taskSchema = {type:'object', additionalProperties:false, required:['action'], properties:{
  action:{type:'string', enum:['start','status','continue','cancel','reject','answer']},
  taskId:string, requestId:{type:'string',description:'Identifiant stable et unique, 8 a 100 caracteres, a reutiliser si resultat incertain.'},
  prompt:string, permissionId:string, questionId:string,
  answers:{type:'array',items:{type:'array',items:string}},
}};
const approvalSchema = {type:'object',additionalProperties:false,required:['taskId','permissionId'],properties:{taskId:string,permissionId:string}};
export default {
  id:'asia-opencode', name:'OpenCode Windows — Asia et Souleiman',
  register(api) {
    for (const [name, parameters, description] of [
      ['asia_opencode_task',taskSchema,'Confier une tache Windows a OpenCode, suivre son resultat, repondre a une question ou annuler. Les autorisations attendent une validation humaine. Ne pas recreer les taches en cours.'],
      ['asia_opencode_approve',approvalSchema,'Presenter au proprietaire une demande OpenCode en attente. Attend son approbation native ; le modele ne peut pas valider seul.'],
    ]) {
      api.registerTool(context => {
        if (!['asia','developpement'].includes(context.agentId)) return null;
        return {name, label:name, description, parameters,
          async execute(callId, params) {
            try {
              const bridge = bridgeFor(context);
              return result(name === 'asia_opencode_approve' ? await bridge.approve(callId, params) :
                params.action === 'status' ? await bridge.status(params.taskId) : await bridge.mutate(params));
            } catch (error) { return {isError:true, content:[{type:'text',text:error.message}]}; }
          },
        };
      }, {name, optional:true});
    }
    api.on('before_tool_call', (event, context) => {
      if (event.toolName !== 'asia_opencode_approve') return;
      try { return bridgeFor(context).approvalHook(event, context); }
      catch (error) { return {block:true, blockReason:error.message}; }
    });
  },
};
