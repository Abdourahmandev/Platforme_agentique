// Execute through stdin with `docker exec -i ... node --input-type=module`.
// Only synthetic data; no Telegram delivery. Never print credentials or results.
import {Client} from '/app/node_modules/@modelcontextprotocol/sdk/dist/esm/client/index.js';
import {StreamableHTTPClientTransport} from '/app/node_modules/@modelcontextprotocol/sdk/dist/esm/client/streamableHttp.js';
import {StdioClientTransport} from '/app/node_modules/@modelcontextprotocol/sdk/dist/esm/client/stdio.js';
import {randomUUID} from 'node:crypto';
import fs from 'node:fs';

const checks = {}, clients = [];
const fixture = 'migration-mcp-' + randomUUID();
function check(name, value) {checks[name]=Boolean(value);}
async function connect(transport) {
  const c=new Client({name:'asia-migration-test',version:'1'},{capabilities:{}});
  clients.push(c); await c.connect(transport); return c;
}
const memoryTransport=()=>new StdioClientTransport({command:'npx',
  args:['--yes','--offline','@modelcontextprotocol/server-memory@1.0.0'],
  env:{PATH:process.env.PATH,HOME:process.env.HOME,
    MEMORY_FILE_PATH:'/home/node/.openclaw/workspaces/asia/memory.jsonl'},stderr:'pipe'});
let memory, browser, created=false;
try {
  const search=await connect(new StreamableHTTPClientTransport(new URL('https://mcp.tavily.com/mcp/'),
    {requestInit:{headers:{Authorization:'Bearer '+process.env.ASIA_TAVILY_API_KEY}}}));
  let result=await search.callTool({name:'tavily_search',arguments:{query:'site:docs.openclaw.ai Telegram',max_results:2,search_depth:'basic'}});
  check('tavily_search',!result.isError && JSON.stringify(result).includes('docs.openclaw.ai'));
  result=await search.callTool({name:'tavily_extract',arguments:{urls:['https://example.com'],extract_depth:'basic'}});
  check('tavily_extract',!result.isError && JSON.stringify(result).includes('Example Domain'));
  memory=await connect(memoryTransport());
  result=await memory.callTool({name:'create_entities',arguments:{entities:[{name:fixture,entityType:'migration-test',observations:['synthetic-persistent-marker']}]}});
  created=!result.isError; check('memory_write',created);
  await memory.close();
  memory=await connect(memoryTransport());
  result=await memory.callTool({name:'open_nodes',arguments:{names:[fixture]}});
  check('memory_survives_process_restart',!result.isError && JSON.stringify(result).includes('synthetic-persistent-marker'));
  browser=await connect(new StreamableHTTPClientTransport(new URL('http://playwright:8931/mcp')));
  result=await browser.callTool({name:'browser_navigate',arguments:{url:'https://example.com'}});
  check('browser_navigation',!result.isError && JSON.stringify(result).includes('Example Domain'));
  result=await browser.callTool({name:'browser_snapshot',arguments:{}});
  check('browser_snapshot',!result.isError && JSON.stringify(result).includes('Example Domain'));
  result=await browser.callTool({name:'browser_navigate',arguments:{url:'file:///etc/passwd'}});
  check('browser_file_url_denied',result.isError===true);
} catch(error) {
  check('suite_completed',false);
  // Retain diagnostics privately in the volume, not in tool output or Git.
  fs.writeFileSync('/home/node/.openclaw/mcp-test-error-private.txt',String(error),{mode:0o600});
} finally {
  if(browser) try {await browser.callTool({name:'browser_close',arguments:{}});} catch {check('browser_cleanup',false);}
  if(created && memory) try {
    const removed=await memory.callTool({name:'delete_entities',arguments:{entityNames:[fixture]}});
    check('memory_fixture_removed',!removed.isError);
  } catch {check('memory_fixture_removed',false);}
  for(const c of clients.reverse()) try {await c.close();} catch {}
}
const result={checks,passed:Object.keys(checks).length>0 && Object.values(checks).every(Boolean)};
console.log(JSON.stringify(result));
process.exitCode=result.passed?0:1;
