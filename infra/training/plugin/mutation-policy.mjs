const workspace='/home/node/.openclaw/workspaces/formation-developpement/';
const allowed=new Set(['repo/infra/task-outcome.mjs','repo/infra/health-report.mjs','repo/test/task-outcome.test.mjs','repo/test/health-report.test.mjs']);
function permitted(value,paths=allowed){
  if(typeof value!=='string'||value.includes('\\')||value.includes('\0'))return false;
  const relative=value.startsWith(workspace)?value.slice(workspace.length):value;
  return paths.has(relative)&&allowed.has(relative);
}
export function mutationError(event,context,policy){
  if(context.agentId!=='formation-developpement')return;
  const paths=policy===undefined?allowed:new Set(Array.isArray(policy)?policy:[]);
  if(['write','edit','fs_write'].includes(event.toolName)){
    if(!permitted(event.params?.path??event.params?.file_path,paths))return 'Ecriture hors des fichiers autorises';
  }
  if(event.toolName==='apply_patch'){
    const patch=event.params?.input;
    if(typeof patch!=='string'||/^\*\*\* (Delete|Move)/m.test(patch))return 'Suppression/deplacement interdit en formation';
    const targets=[...patch.matchAll(/^\*\*\* (?:Add|Update) File: (.+)$/gm)].map(m=>m[1].trim());
    if(!targets.length||targets.some(p=>!permitted(p,paths)))return 'Patch hors des fichiers autorises';
  }
}
