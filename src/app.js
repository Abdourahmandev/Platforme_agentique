import { marked } from 'marked';
import DOMPurify from 'dompurify';
import { submissionIdentity, clearSubmission } from './submission.js';
import { createIcons, Menu, X, Plus, Search, Settings2, Sun, Moon, ArrowUp, Square, MessageCircle, Files, Sparkles, SquareCheck, SlidersHorizontal, Activity, ShieldCheck, FileText, Check, Circle, LoaderCircle, ExternalLink, ChevronRight, ChevronDown, RefreshCw, Paperclip, Download, Terminal, CircleHelp } from 'lucide';
const iconSet = {Menu,X,Plus,Search,Settings2,Sun,Moon,ArrowUp,Square,MessageCircle,Files,Sparkles,SquareCheck,SlidersHorizontal,Activity,ShieldCheck,FileText,Check,Circle,LoaderCircle,ExternalLink,ChevronRight,ChevronDown,RefreshCw,Paperclip,Download,Terminal,CircleHelp};
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icon = name => `<i data-lucide="${name}" aria-hidden="true"></i>`;
const icons = () => createIcons({icons: iconSet});
const storage = {get(k){try{return localStorage.getItem(k)}catch{return null}},set(k,v){try{localStorage.setItem(k,v)}catch{}}};
const state = { bootstrap:null, profile:"auto", profileUpdating:false, routing:null, sessions:[], selected:storage.get('asia.session'), view:'chat', messages:[], todos:[], diff:[], permissions:[], questions:[], status:{type:'idle'}, statuses:{}, files:[], sending:false, connected:false, loading:false, requestGeneration:0, theme:storage.get('asia.theme') || 'dark' };
let events, refreshTimer, toastTimer, refreshing=false, refreshAgain=false, pendingSince=0, installPrompt=null;
function markdown(text) { return DOMPurify.sanitize(marked.parse(text || '', {gfm:true,breaks:true}), { FORBID_TAGS:['img','style','form','input','button','iframe'], FORBID_ATTR:['style'], ADD_ATTR:['target'] }); }
function setTheme(theme) { state.theme=theme==='light'?'light':'dark'; document.documentElement.dataset.theme=state.theme; storage.set('asia.theme',state.theme); $('meta[name="theme-color"]').content=state.theme==='light'?'#ffffff':'#090909'; $('#theme-toggle').innerHTML=icon(state.theme==='dark'?'sun':'moon');$('#theme-toggle').setAttribute('aria-label',state.theme==='dark'?'Passer au fond blanc':'Passer au fond noir'); icons(); }
function toast(text) { $('#toast').textContent=text;$('#toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').hidden=true,4500); }
function fail(error) { $('#error-banner span').textContent=error.message||String(error);$('#error-banner').hidden=false; }
function clearError() { $('#error-banner').hidden=true; }
async function api(url, options={}) {
  const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),35000);
  try { const res=await fetch('/api'+url,{method:options.method||'GET',headers:options.method?{'Content-Type':'application/json','X-Asia-CSRF':state.bootstrap?.csrf||''}:{},body:options.data?JSON.stringify(options.data):undefined,signal:controller.signal,cache:'no-store'});
    const data=await res.json();
    if(!res.ok && data.code==='csrf_invalid' && !options.csrfRetried){state.bootstrap=await api('/bootstrap');return api(url,{...options,csrfRetried:true});}
    if(!res.ok)throw Object.assign(new Error(data.error||`Erreur ${res.status}`),{code:data.code,status:res.status,requestId:data.requestId});return data;
  } catch(error) { if(error.name==='AbortError')throw new Error('Le serveur ne répond pas. Vérifie la connexion puis réessaie.');throw error; } finally {clearTimeout(timer);}
}
function session() { return state.sessions.find(s=>s.id===state.selected); }
function busy() { return state.sending || state.status.type==='busy' || state.status.type==='retry'; }
function date(ts) { return new Date(ts).toLocaleDateString('fr-FR',{day:'numeric',month:'short'}); }
function showSidebar(open) {$('#sidebar').classList.toggle('open',open);$('#sidebar-scrim').hidden=!open;}
function renderSessions() {const query=$('#session-search').value.toLocaleLowerCase();const list=state.sessions.filter(s=>(s.title||'Conversation').toLocaleLowerCase().includes(query));$('#sessions').innerHTML=list.length?list.map(s=>`<button class="session-item ${s.id===state.selected?'active':''}" data-session="${esc(s.id)}"><span>${esc(s.title||'Conversation')}</span><small>${date(s.time?.updated||s.time?.created||Date.now())}${state.statuses[s.id]?.type==='busy'?' · En cours':''}</small></button>`).join(''):`<p class="muted">${query?'Aucune conversation trouvée.':'Tes conversations apparaîtront ici.'}</p>`;}
function setView(view) {state.view=view;render();if(view==='settings')api('/routing').then(data=>{state.routing=data;if(state.view==='settings')render();}).catch(fail);}
function statusText() { if(!state.connected)return 'Connexion interrompue';if(state.permissions.length||state.questions.length)return 'Une réponse est attendue';if(state.status.type==='retry')return 'Nouvelle tentative en cours';if(busy())return 'Asia travaille…';return 'Prête à t’aider'; }
function activeProfile(){return state.bootstrap?.profiles?.find(p=>p.id===state.profile);}
function renderProfile(){const select=$('#model-profile');const profiles=state.bootstrap?.profiles||[];const options=profiles.map(p=>`<option value="${esc(p.id)}">${esc(p.label)} · ${esc(p.description)}</option>`).join('');if(options && select.innerHTML!==options)select.innerHTML=options;select.value=state.profile;select.disabled=busy()||state.loading||state.profileUpdating;$('#profile-lock').textContent=busy()?'Fixé pendant la tâche':state.profile==='auto'?'Choix automatique':state.profile==='rapide'?'Repli économique':'';}
function routingCard(){const t=state.routing?.totals;const models=state.routing?.models||[];return `<section class="item-card"><h3>Auto économique · LiteLLM</h3><p>Demandes simples : DeepSeek Flash. Niveau intermédiaire : Gemini 3.1 Flash-Lite. Tâches complexes : Gemini 3.8 Flash. Raisonnement avancé : Gemini 3.1 Pro.</p><p>Le choix utilise des règles locales, sans appel payant de classification. Tu peux aussi choisir un modèle manuellement au-dessus du message.</p><p>Une seule tentative de repli par appel. Réponses Auto limitées à 8 192 tokens. Plafond de la clé agent : ${Number(state.bootstrap?.limits?.budgetUSD || 0)} $ US sur 30 jours ; les appels déjà en cours peuvent dépasser ce seuil.</p>${t?`<p>${t.success} appels réussis · ${t.errors} tentatives en erreur<br>${(t.inputTokens+t.outputTokens).toLocaleString('fr-FR')} tokens · coût estimé : ${t.estimatedUSD.toFixed(4)} $ US${t.unpriced?` (${t.unpriced} tentatives non chiffrées)`:''}</p>${models.map(m=>`<p><strong>${esc(m.model)}</strong><br>${m.calls} appels · ${m.estimatedUSD.toFixed(4)} $ US</p>`).join('')}<p class="muted">Cumul du journal local. Estimations indicatives ; la facturation finale dépend de Google et DeepSeek.</p>`:''}</section>`;}

function renderChrome() {
  $('.workspace').dataset.view=state.view;$('.workspace').dataset.conversation=String(!!state.selected);
  $('.workspace').dataset.connected=String(state.connected);
  $('#session-title').textContent=session()?.title||'Asia';
  $('#connection-label').textContent=state.connected?`${activeProfile()?.label || 'DeepSeek'} · connexion privée`:'Connexion au serveur…';$('#connection-label').classList.toggle('connection-error',!state.connected);
  $('#context-status').textContent=statusText();$('#context-detail').textContent=state.permissions.length?'Une action nécessite ton accord.':state.questions.length?'Asia a besoin d’une précision pour continuer.':busy()?'Tu peux suivre son activité ou arrêter la tâche.':'Les actions et les prochaines étapes de la conversation sont réunies ici.';
  $('#context-todos').innerHTML=state.todos.slice(0,5).map(t=>`<div class="mini-todo ${t.status==='completed'?'done':''}">${icon(t.status==='completed'?'check':'circle')}<span>${esc(t.content)}</span></div>`).join('');
  $$('.bottom-nav button').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.view===state.view)));
  $('#composer-zone').hidden=state.view!=='chat';$('#send-button').hidden=busy();$('#stop-button').hidden=!busy();$('#stop-button').disabled=state.sending;$('#message-input').disabled=state.sending||state.loading||!state.bootstrap;$('#send-button').disabled=!state.connected||state.loading||state.sending||state.profileUpdating;renderProfile();
  $('#composer-note').textContent=busy()?statusText():'Contexte envoyé au modèle choisi · historique sur ton PC';
}
function empty(title,desc) { return `<div class="empty"><h2>${esc(title)}</h2><p>${esc(desc)}</p></div>`; }
function activityParts() {return state.messages.flatMap(m=>(m.parts||[]).filter(p=>p.type==='tool').map(p=>({...p,messageID:m.info?.id})));}
function toolMarkup(p) {const s=p.state||{};const labels={pending:'En attente',running:'En cours',completed:'Terminée',error:'Erreur'};const detail=s.error||s.output||JSON.stringify(s.input||{},null,2);return `<details class="activity-item"><summary>${icon('terminal')}<span>${esc(s.title||p.tool||'Action')}</span><small class="badge">${labels[s.status]||s.status||''}</small></summary><pre>${esc(typeof detail==='string'?detail:JSON.stringify(detail,null,2))}</pre></details>`;}
function renderChat() {
  if(state.loading)return empty('Ouverture de la conversation…','Récupération des messages sur ton PC.');
  if(!state.messages.length)return `<div class="empty"><h2>Qu’as-tu en tête ?</h2><p>Un projet à avancer, une question à éclaircir.<br>On commence ici.</p><div class="suggestions"><button class="suggestion" data-suggest="Aide-moi à préparer un plan pour mon projet.">${icon('plus')}<span>Préparer un projet<small>Passer de l’idée au plan</small></span>${icon('chevron-right')}</button><button class="suggestion" data-suggest="Explique-moi les fichiers du projet, sans les modifier.">${icon('files')}<span>Comprendre mon projet<small>Explorer les fichiers ensemble</small></span>${icon('chevron-right')}</button><button class="suggestion" data-suggest="Fais le point sur ce que nous avons accompli dans cette conversation.">${icon('square-check')}<span>Faire le point<small>Retrouver les prochaines étapes</small></span>${icon('chevron-right')}</button></div></div>`;
  return `<div class="day-label">${date(state.messages[0]?.info?.time?.created||Date.now())}</div>`+state.messages.map(m=>{
    const role=m.info?.role;const text=(m.parts||[]).filter(p=>p.type==='text'&&!p.ignored).map(p=>p.text).join('\n\n');const tools=(m.parts||[]).filter(p=>p.type==='tool');const attachments=(m.parts||[]).filter(p=>p.type==='file');const error=m.info?.error;
    const attachmentHTML=attachments.map(p=>`<div class="attachment-chip">${icon('paperclip')}${esc(p.filename||'Pièce jointe')}</div>`).join('');
    const stamp=m.info?.time?.created?new Date(m.info.time.created).toLocaleTimeString('fr-FR',{hour:'2-digit',minute:'2-digit'}):'';
    return `${text||attachmentHTML||error?`<article class="message ${role==='user'?'user':'assistant'}">${text?markdown(text):''}${attachmentHTML}${error?`<p class="connection-error">${esc(error.data?.message||error.message||error.name||'Cette réponse a été interrompue.')}</p>`:''}<div class="message-meta"><span>${role==='user'?'Toi':'Asia'}</span><span>${stamp}</span></div></article>`:''}${tools.length?`<details class="inline-activity"><summary>${tools.length} action${tools.length>1?'s':''} · afficher les détails</summary>${tools.map(toolMarkup).join('')}</details>`:''}`;
  }).join('')+(busy()?`<div class="busy-indicator" role="status">${icon('sparkles')}<span>${esc(statusText())}</span></div>`:'');
}
function renderFiles() { return `<div class="section-heading"><h2>Fichiers modifiés</h2></div>`+(state.diff.length?state.diff.map((f,i)=>`<button class="item-card file-card" data-diff="${i}"><span class="file-icon">${icon('file-text')}</span><span>${esc(f.file)}<small>+${Number(f.additions)||0} / −${Number(f.deletions)||0} lignes · voir les modifications</small></span></button>`).join(''):empty('Aucune modification','Les fichiers modifiés par l’agent dans cette conversation apparaîtront ici.')); }
function renderTasks() {const labels={pending:'À faire',in_progress:'En cours',completed:'Terminée',cancelled:'Annulée'};return `<div class="section-heading"><h2>Les prochaines étapes</h2></div>`+(state.todos.length?state.todos.map(t=>`<article class="item-card task ${t.status==='completed'?'done':''}">${icon(t.status==='completed'?'square-check':'circle')}<div><span class="task-title">${esc(t.content)}</span><small>${labels[t.status]||esc(t.status)}</small></div></article>`).join(''):empty('Pas encore de plan','Lorsqu’Asia crée une liste d’étapes pour ta demande, tu peux la suivre ici.')); }
function renderSettings() {const b=state.bootstrap;return `<div class="section-heading"><h2>À ta façon</h2></div><section class="item-card"><div class="settings-row"><span>Apparence</span><div class="theme-options"><button data-theme="dark" aria-pressed="${state.theme==='dark'}">Noir</button><button data-theme="light" aria-pressed="${state.theme==='light'}">Blanc</button></div></div><p>Ton choix est conservé sur cet appareil.</p></section>${routingCard()}<section class="item-card"><h3>Ton agent</h3><p>OpenCode · ${esc(activeProfile()?.description||b?.model?.modelID||'DeepSeek')}</p><p>${esc(b?.directory||'Connexion en cours…')}</p><p>${state.connected?'Serveur connecté':'Serveur indisponible'}</p></section><section class="item-card"><h3>Toujours à portée de main</h3><button class="link-btn" data-action="install">${icon('download')}Installer sur cet appareil</button><button class="link-btn" data-action="copy-link">${icon('external-link')}Copier le lien privé</button>${b?.telegramURL?`<a class="link-btn" href="${esc(b.telegramURL)}" target="_blank" rel="noopener noreferrer">${icon('message-circle')}Ouvrir mon bot Telegram</a>`:''}<p>Garde Tailscale actif et le PC allumé pour accéder à Asia à distance.</p></section>`; }
function renderRequests() {
  const area=$('#request-area');const currentKey=JSON.stringify([state.permissions,state.questions,state.submissions]);if(area.dataset.key===currentKey)return;area.dataset.key=currentKey;
  area.innerHTML=state.permissions.map(p=>`<section class="request-card"><h3>Ton accord est nécessaire</h3><p>${esc(p.permission)}</p><pre>${esc((p.patterns||[]).join('\n'))}</pre><div class="actions"><button class="action primary" data-permission="${esc(p.id)}" data-reply="once">Autoriser une fois</button><button class="action" data-permission="${esc(p.id)}" data-reply="reject">Refuser</button></div></section>`).join('')+state.questions.map(q=>`<form class="request-card question-form" data-question="${esc(q.id)}">${q.questions.map((question,i)=>`<h3>${esc(question.question)}</h3>${question.options.map((o,j)=>`<label class="question-label"><input type="${question.multiple?'checkbox':'radio'}" name="q${i}" value="${esc(o.label)}"> ${esc(o.label)}${o.description?` — ${esc(o.description)}`:''}</label>`).join('')}<input class="question-input" name="free${i}" placeholder="Ta réponse, si différente…" aria-label="Réponse libre à ${esc(question.header||question.question)}">`).join('')}<div class="actions"><button type="submit" class="action primary">Répondre</button><button type="button" class="action" data-reject-question="${esc(q.id)}">Ignorer</button></div></form>`).join('');
  area.innerHTML+=(state.submissions||[]).filter(s=>s.state==='uncertain').map(s=>`<section class="request-card"><h3>Envoi à vérifier</h3><p>La confirmation a été interrompue. Vérifie les derniers messages avant de poursuivre ; cet envoi ne sera pas répété automatiquement.</p><button class="action" data-abandon-submission="${esc(s.id)}">Abandonner cet envoi</button></section>`).join('');
}
function render() {
  const scroller=$('#scroll-area'),nearBottom=scroller.scrollHeight-scroller.scrollTop-scroller.clientHeight<130;const oldScroll=scroller.scrollTop;
  const body=state.view==='chat'?renderChat():state.view==='files'?renderFiles():state.view==='tasks'?renderTasks():state.view==='settings'?renderSettings():`<div class="section-heading"><h2>Ce qu’Asia fait</h2></div>${activityParts().length?activityParts().map(toolMarkup).join(''):empty('Tout est calme','Les commandes, recherches et autres actions de cette conversation apparaîtront ici.')}`;
  const content=$('#main-content');if(content.innerHTML!==body){const open=[...content.querySelectorAll('details')].map((d,i)=>d.open?i:-1);content.innerHTML=body;content.querySelectorAll('details').forEach((d,i)=>d.open=open.includes(i));}
  renderChrome();renderRequests();icons();if(state.view==='chat'&&nearBottom)scroller.scrollTop=scroller.scrollHeight;else scroller.scrollTop=oldScroll;
}
async function listSessions() {const sessions=await api('/sessions');state.sessions=Array.isArray(sessions)?sessions:[];renderSessions();}
async function refresh() {
  if(!state.selected||!state.bootstrap)return;
  if(refreshing){refreshAgain=true;return;}refreshing=true;const id=state.selected;const generation=state.requestGeneration;
  try {const [messages,todos,diff,requests]=await Promise.all(['messages','todos','diff','requests'].map(s=>api(`/sessions/${id}/${s}`)));
    if(id!==state.selected||generation!==state.requestGeneration)return;
    state.messages=messages;state.todos=todos;state.diff=diff;state.permissions=requests.permissions;state.questions=requests.questions;state.submissions=requests.submissions||[];state.status=requests.status;state.profile=requests.profile || state.bootstrap?.defaultProfile || 'auto';state.connected=true;state.loading=false;
    if(pendingSince&&Date.now()-pendingSince<2500&&state.status.type==='idle')state.status={type:'busy'};else pendingSince=0;
    render();
  }catch(error){if(id===state.selected){state.loading=false;state.connected=false;fail(error);render();}}
  finally{refreshing=false;if(refreshAgain){refreshAgain=false;queueMicrotask(refresh);}}
}
async function selectSession(id) {
  if(state.sending||state.profileUpdating){toast('Attends la confirmation avant de changer de conversation.');return;}
  state.selected=id;state.profile=state.sessions.find(s=>s.id===id)?.metadata?.asiaProfile || state.bootstrap?.defaultProfile || 'auto';storage.set('asia.session',id||'');state.requestGeneration++;state.messages=[];state.todos=[];state.diff=[];state.permissions=[];state.questions=[];state.submissions=[];state.status={type:'idle'};state.files=[];pendingSince=0;state.loading=!!id;state.view='chat';renderAttachments();showSidebar(false);clearError();renderSessions();render();if(id)await refresh();$('#scroll-area').scrollTop=$('#scroll-area').scrollHeight;
}
function connectEvents() {
  events?.close();events=new EventSource('/api/events');events.onopen=()=>{state.connected=true;renderChrome();refresh();};events.onerror=()=>{state.connected=false;renderChrome();};
  events.onmessage=e=>{let event;try{event=JSON.parse(e.data)}catch{return;}const payload=event.payload||event;const type=payload.type||'';if(type.includes('heartbeat')||type.includes('connected'))return;
    const p=payload.properties||{};const sid=p.sessionID||p.info?.sessionID||p.part?.sessionID||p.info?.id;
    if(type.includes('session.updated')||type.includes('session.created')||type.includes('session.deleted'))listSessions().catch(()=>{});
    if(type==='session.status'&&p.sessionID)state.statuses[p.sessionID]=p.status;
    if(!sid||sid===state.selected){clearTimeout(refreshTimer);refreshTimer=setTimeout(refresh,250);}
  };
}
async function start() {try{state.bootstrap=await api('/bootstrap');state.connected=true;clearError();await listSessions();if(state.selected&&!state.sessions.some(s=>s.id===state.selected))state.selected=null;await selectSession(state.selected);connectEvents();}catch(error){state.connected=false;fail(error);render();}}
async function sendMessage(event) {
  event.preventDefault();const text=$('#message-input').value.trim();if(!text||busy()||state.profileUpdating)return;clearError();state.sending=true;renderChrome();
  try {
    if(!state.selected){const s=await api('/sessions',{method:'POST',data:{title:text.slice(0,70),profile:state.profile}});state.sessions.unshift(s);state.selected=s.id;storage.set('asia.session',s.id);renderSessions();}
    const payload={text,attachments:state.files};
    const requestId=await submissionIdentity(state.selected,payload);
    await api(`/sessions/${state.selected}/prompt`,{method:'POST',data:{...payload,requestId}});
    clearSubmission(state.selected);
    $('#message-input').value='';$('#message-input').style.height='';state.files=[];renderAttachments();state.status={type:'busy'};pendingSince=Date.now();state.messages.push({info:{role:'user',time:{created:Date.now()}},parts:[{type:'text',text}]});state.sending=false;render();$('#scroll-area').scrollTop=$('#scroll-area').scrollHeight;setTimeout(refresh,700);
  }catch(error){if(error.code==='prompt_rejected')clearSubmission(state.selected);state.sending=false;fail(error);renderChrome();}
}
function renderAttachments() {$('#attachment-list').innerHTML=state.files.map((f,i)=>`<span class="attachment-chip">${icon('paperclip')}${esc(f.name)}<button data-remove-file="${i}" aria-label="Retirer ${esc(f.name)}">${icon('x')}</button></span>`).join('');icons();}
function openDiff(index) {const f=state.diff[index];if(!f)return;$('#detail-title').textContent=f.file;$('#detail-content').innerHTML=`<p class="diff-label">Avant</p><pre class="diff-removed">${esc(f.before||'(nouveau fichier)')}</pre><p class="diff-label">Après</p><pre class="diff-added">${esc(f.after||'(fichier supprimé)')}</pre>`;$('#detail-dialog').showModal();}
document.addEventListener('click',async event=>{
  const button=event.target.closest('button');if(!button)return;
  if(button.dataset.abandonSubmission){
    if(!confirm('Cet envoi a peut-être déjà été reçu. Après avoir vérifié la conversation, veux-tu abandonner sa confirmation sans le renvoyer ?'))return;
    button.disabled=true;
    try{const result=await api(`/sessions/${state.selected}/submissions/${button.dataset.abandonSubmission}/abandon`,{method:'POST',data:{acknowledgePossibleDelivery:true}});clearSubmission(state.selected);toast(result.accepted?'Le message avait bien été reçu.':'Envoi abandonné sans répétition.');await refresh();}catch(error){fail(error);button.disabled=false;}return;
  }
  if(button.dataset.session){await selectSession(button.dataset.session);return;}
  if(button.dataset.view){setView(button.dataset.view);return;}
  if(button.dataset.theme){setTheme(button.dataset.theme);render();return;}
  if(button.dataset.suggest){$('#message-input').value=button.dataset.suggest;$('#message-input').focus();return;}
  if(button.dataset.diff!==undefined){openDiff(Number(button.dataset.diff));return;}
  if(button.dataset.removeFile!==undefined){state.files.splice(Number(button.dataset.removeFile),1);renderAttachments();return;}
  if(button.dataset.permission){button.disabled=true;try{await api(`/sessions/${state.selected}/permission/${button.dataset.permission}/reply`,{method:'POST',data:{reply:button.dataset.reply}});toast('Réponse transmise à l’agent.');await refresh();}catch(error){fail(error);button.disabled=false;}return;}
  if(button.dataset.rejectQuestion){button.disabled=true;try{await api(`/sessions/${state.selected}/question/${button.dataset.rejectQuestion}/reject`,{method:'POST',data:{}});await refresh();}catch(error){fail(error);button.disabled=false;}return;}
  if(button.dataset.action==='copy-link'){try{await navigator.clipboard.writeText(state.bootstrap.publicURL);toast('Lien privé copié.');}catch{toast(state.bootstrap?.publicURL||location.origin);}return;}
  if(button.dataset.action==='install'){if(installPrompt){await installPrompt.prompt();installPrompt=null;}else toast('Dans le menu du navigateur, choisis « Ajouter à l’écran d’accueil » ou « Installer l’application ».');return;}
});
document.addEventListener('submit',async event=>{const form=event.target.closest('.question-form');if(!form)return;event.preventDefault();const question=state.questions.find(q=>q.id===form.dataset.question);if(!question)return;const fd=new FormData(form);const answers=question.questions.map((q,i)=>{const free=String(fd.get(`free${i}`)||'').trim();return free?[free]:fd.getAll(`q${i}`);});if(answers.some(a=>!a.length)){toast('Réponds à chaque question avant de continuer.');return;}const submit=form.querySelector('[type=submit]');submit.disabled=true;try{await api(`/sessions/${state.selected}/question/${question.id}/reply`,{method:'POST',data:{answers}});await refresh();}catch(error){fail(error);submit.disabled=false;}});
$('#model-profile').addEventListener('change',async e=>{const previous=state.profile;const next=e.target.value;state.profileUpdating=true;state.requestGeneration++;renderChrome();try{if(state.selected){await api(`/sessions/${state.selected}/profile`,{method:'POST',data:{profile:next}});const s=session();if(s)s.metadata={...s.metadata,asiaProfile:next};}state.profile=next;toast(`Profil ${activeProfile()?.label || next} sélectionné.`);}catch(error){state.profile=previous;fail(error);}finally{state.profileUpdating=false;state.requestGeneration++;renderChrome();refresh();}});
$('#composer').addEventListener('submit',sendMessage);
$('#message-input').addEventListener('input',e=>{e.target.style.height='auto';e.target.style.height=Math.min(e.target.scrollHeight,150)+'px';});
$('#message-input').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing&&matchMedia('(min-width:721px)').matches){e.preventDefault();$('#composer').requestSubmit();}});
$('#new-chat').addEventListener('click',()=>selectSession(null));$('#session-search').addEventListener('input',renderSessions);
$('#open-sidebar').addEventListener('click',()=>showSidebar(true));$('#close-sidebar').addEventListener('click',()=>showSidebar(false));$('#sidebar-scrim').addEventListener('click',()=>showSidebar(false));$('#sidebar-settings').addEventListener('click',()=>{showSidebar(false);setView('settings');});
$('#theme-toggle').addEventListener('click',()=>{setTheme(state.theme==='dark'?'light':'dark');if(state.view==='settings')render();});
$('#retry').addEventListener('click',start);$('#close-dialog').addEventListener('click',()=>$('#detail-dialog').close());
$('#stop-button').addEventListener('click',async()=>{if(!state.selected)return;$('#stop-button').disabled=true;try{await api(`/sessions/${state.selected}/abort`,{method:'POST'});pendingSince=0;state.status={type:'idle'};toast('Arrêt demandé.');await refresh();}catch(error){fail(error);}finally{renderChrome();}});
$('#attach-file').addEventListener('click',()=>$('#file-input').click());
$('#file-input').addEventListener('change',async e=>{for(const file of e.target.files){if(state.files.length>=3){toast('Trois fichiers maximum par message.');break;}if(file.size>150000){toast(`${file.name} dépasse 150 Ko.`);continue;}if(!/\.(txt|md|csv|json|js|ts|py|sql|html|css|yaml|yml|log)$/i.test(file.name)){toast('Choisis un fichier texte ou de code.');continue;}state.files.push({name:file.name,text:await file.text()});}e.target.value='';renderAttachments();});
window.addEventListener('beforeinstallprompt',e=>{e.preventDefault();installPrompt=e;});
window.addEventListener('online',()=>start());document.addEventListener('visibilitychange',()=>{if(!document.hidden){refresh();listSessions().catch(()=>{});}});
setInterval(()=>{if(!document.hidden&&state.selected)refresh();},10000);
setTheme(state.theme);render();start();
if('serviceWorker' in navigator)navigator.serviceWorker.register('/sw.js').catch(()=>{});
