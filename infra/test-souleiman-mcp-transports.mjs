// Run through stdin inside OpenClaw. Only read-only calls, no private content output.
import {Client} from '/app/node_modules/@modelcontextprotocol/sdk/dist/esm/client/index.js';
import {StreamableHTTPClientTransport} from '/app/node_modules/@modelcontextprotocol/sdk/dist/esm/client/streamableHttp.js';
import fs from 'node:fs';
const checks={},clients=[];
function check(name,value){checks[name]=Boolean(value);if(!value)throw Error('Failed: '+name);}
async function connect(url,headers){
  const c=new Client({name:'souleiman-connector-test',version:'1'},{capabilities:{}});
  clients.push(c);await c.connect(new StreamableHTTPClientTransport(new URL(url),{requestInit:{headers}}));return c;
}
function resultText(r){
  const raw=JSON.stringify(r);
  let decoded=raw;
  for(const p of r.content||[])if(p.type==='text'){
    try{const v=JSON.parse(p.text);if(v.encoding==='base64')decoded+=Buffer.from(v.content,'base64').toString('utf8');}catch{}
  }
  return decoded;
}
try{
  const context=await connect('https://mcp.context7.com/mcp');
  const resolved=await context.callTool({name:'resolve-library-id',arguments:{libraryName:'Playwright',query:'Official browser testing documentation'}});
  check('context7_library_lookup',!resolved.isError&&resultText(resolved).includes('/microsoft/playwright'));
  const docs=await context.callTool({name:'query-docs',arguments:{libraryId:'/microsoft/playwright',query:'How to assert that a page has a title with Playwright Test?'}});
  check('context7_documentation',!docs.isError&&resultText(docs).includes('toHaveTitle'));
  const github=await connect('https://api.githubcopilot.com/mcp/',{Authorization:'Bearer '+process.env.SOULEIMAN_GITHUB_TOKEN,'X-MCP-Toolsets':'repos,issues,pull_requests,actions'});
  const configured=JSON.parse(fs.readFileSync('/home/node/.openclaw/openclaw.json')).mcp.servers.github.toolFilter.include;
  const advertised=(await github.listTools()).tools.map(t=>t.name);
  check('github_selected_tools_exist',configured.every(t=>advertised.includes(t)));
  const repository=await github.callTool({name:'get_file_contents',arguments:{owner:'Abdourahmandev',repo:'Platforme_agentique',path:'package.json',ref:'refs/heads/main'}});
  check('github_private_repository_read',!repository.isError&&resultText(repository).includes('asia-agent-app'));
  const actions=await github.callTool({name:'actions_list',arguments:{method:'list_workflow_runs',owner:'Abdourahmandev',repo:'Platforme_agentique',per_page:1}});
  check('github_actions_read',!actions.isError&&resultText(actions).includes('workflow_runs'));
}catch(e){
  checks.completed=false;
  fs.writeFileSync('/home/node/.openclaw/souleiman-connectors-error-private.txt',String(e),{mode:0o600});
}finally{for(const c of clients.reverse())try{await c.close();}catch{}}
console.log(JSON.stringify({checks,passed:Object.values(checks).every(Boolean)}));
process.exitCode=Object.values(checks).every(Boolean)?0:1;
