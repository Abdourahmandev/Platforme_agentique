// Persist only the identity and hash, never the message or attachment content.
export async function submissionIdentity(sessionID,payload,store=localStorage) {
  const bytes=new TextEncoder().encode(JSON.stringify(payload));
  const hash=[...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(x=>x.toString(16).padStart(2,'0')).join('');
  const key='asia.pending.'+sessionID;
  let saved;try{saved=JSON.parse(store.getItem(key)||'null');}catch{}
  if(saved?.hash===hash && saved.requestId)return saved.requestId;
  const requestId=crypto.randomUUID();store.setItem(key,JSON.stringify({requestId,hash}));return requestId;
}
export function clearSubmission(sessionID,store=localStorage){store.removeItem('asia.pending.'+sessionID);}
