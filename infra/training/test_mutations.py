"""Exercise the deployed plugin hook without asking a model to write files.

The Gateway HTTP tools endpoint does not expose the embedded file tools (404).
Invoke the installed hook inside its service container and inspect its verdict.
"""
import json
from common import BASE, STATE, node

script='''(async()=>{
 const plugin=(await import("file:///home/node/.openclaw/extensions/asia-training/index.mjs")).default;
 let hook;plugin.register({registerTool(){},on(name,fn){if(name==="before_tool_call")hook=fn;}});
 const ctx={agentId:"formation-developpement"};
 const cases=[
  {toolName:"write",params:{path:"repo/formation-denied-probe.txt",content:"FIXTURE"}},
  {toolName:"edit",params:{path:"AGENTS.md",oldText:"NEVER_MATCH",newText:"FIXTURE"}},
  {toolName:"apply_patch",params:{input:"*** Begin Patch\\n*** Add File: .openclaw/tmp/formation-denied-probe.txt\\n+FIXTURE\\n*** End Patch"}}
 ];
 const result=cases.map(v=>({tool:v.toolName,...hook(v,ctx)}));
 if(result.some(v=>!v.block||!v.blockReason.includes("fichiers autorises")))throw Error("Mutation guard did not reject forbidden path");
 if(hook({toolName:"edit",params:{path:"repo/test/task-outcome.test.mjs"}},ctx)!==undefined)throw Error("Allowed path blocked");
 console.log(JSON.stringify({checks:result,allowed_path_preserved:true,method:"installed before_tool_call hook; no file mutation"}));
})().catch(e=>{console.error(e.message);process.exitCode=1;});'''

if __name__=='__main__':
    result=json.loads(node(script))
    (STATE/'mutation-preflight.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result))
