const workspace='/home/node/.openclaw/workspaces/formation-developpement/';
const allowed=new Set(['repo/infra/task-outcome.mjs','repo/infra/health-report.mjs','repo/test/task-outcome.test.mjs','repo/test/health-report.test.mjs']);
function permitted(value){
  if(typeof value!=='string'||value.includes('\\')||value.includes('\0'))return false;
  const relative=value.startsWith(workspace)?value.slice(workspace.length):value;
  return allowed.has(relative);
}
export function mutationError(event,context){
  if(context.agentId!=='formation-developpement')return;
  if(['write','edit','fs_write'].includes(event.toolName)){
    if(!permitted(event.params?.path??event.params?.file_path))return 'Ecriture hors des quatre fichiers autorises';
  }
  if(event.toolName==='apply_patch'){
    const patch=event.params?.input;
    if(typeof patch!=='string'||/^\*\*\* (Delete|Move)/m.test(patch))return 'Suppression/deplacement interdit en formation';
    const paths=[...patch.matchAll(/^\*\*\* (?:Add|Update) File: (.+)$/gm)].map(m=>m[1].trim());
    if(!paths.length||paths.some(p=>!permitted(p)))return 'Patch hors des quatre fichiers autorises';
  }
}
