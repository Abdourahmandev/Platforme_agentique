// Asia's Notion tool: talks only to the internal notion-bridge, which is limited to the
// "Projets Decidata" database. The bridge URL and key come from credentials.json (`notion`).
const ROUTES={
  list:()=>['GET','/projects'],
  setup:()=>['POST','/setup'],
  create:p=>['POST','/projects',{fields:p.fields}],
  update:p=>['PATCH',`/projects/${p.projectId}`,{fields:p.fields}],
  add_section:p=>['POST',`/projects/${p.projectId}/sections`,{title:p.title,text:p.text}],
};

export async function notionCall(config,params,fetchImpl=fetch){
  if(!config?.url||!config?.key)throw new Error('Notion n est pas configure sur la plateforme.');
  const route=ROUTES[params.action];
  if(!route)throw new Error('Action Notion inconnue : '+params.action);
  if(['update','add_section'].includes(params.action)&&!/^[0-9a-f-]{32,36}$/.test(params.projectId||''))
    throw new Error('projectId (identifiant de la fiche, voir list) est requis.');
  const [method,path,body]=route(params);
  const response=await fetchImpl(config.url.replace(/\/+$/,'')+path,{method,
    headers:{Authorization:'Bearer '+config.key,'Content-Type':'application/json'},
    body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(60000)});
  const value=await response.json().catch(()=>({}));
  if(!response.ok)throw new Error(value.error||('Relais Notion : HTTP '+response.status));
  return value;
}
