import http from 'node:http';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { randomBytes } from 'node:crypto';
import { Readable } from 'node:stream';
import { RequestJournal, fingerprint, validRequestId } from './request-journal.mjs';

const root = path.dirname(fileURLToPath(import.meta.url));
export function profileFor(config, id) {
  const profiles = config.profiles || [{ id:'pro', label:'Approfondi', ...config.model }];
  const profile = profiles.find(p => p.id === (id || config.defaultProfile || 'pro'));
  if (!profile) throw Object.assign(new Error('Profil de modèle inconnu.'), { status: 400 });
  return profile;
}
export function authorize(req, config) {
  if (!['127.0.0.1', '::1', '::ffff:127.0.0.1'].includes(req.socket.remoteAddress)) return false;
  const host = req.headers.host?.toLowerCase();
  const local = [`127.0.0.1:${config.port}`, `localhost:${config.port}`].includes(host);
  if (local) return !req.headers['x-forwarded-for'] && !req.headers['tailscale-user-login'];
  return host === config.publicHost.toLowerCase() && req.headers['tailscale-user-login']?.toLowerCase() === config.ownerLogin.toLowerCase();
}
export function validMutation(req, csrf) {
  if (req.headers['x-asia-csrf'] !== csrf) return false;
  try {
    const origin = new URL(req.headers.origin);
    return origin.host.toLowerCase() === req.headers.host?.toLowerCase() && ['http:', 'https:'].includes(origin.protocol);
  } catch { return false; }
}
async function body(req) {
  let size = 0; const chunks = [];
  for await (const chunk of req) { size += chunk.length; if (size > 8 * 1024 * 1024) throw Object.assign(new Error('Message trop volumineux (8 Mo maximum).'), { status: 413 }); chunks.push(chunk); }
  try { return JSON.parse(Buffer.concat(chunks).toString() || '{}'); } catch { throw Object.assign(new Error('Requête JSON invalide.'), { status: 400 }); }
}
export function createApp(config) {
  const csrf = randomBytes(32).toString('hex');
  const journal=new RequestJournal(config.requestDBPath || path.join(process.env.LOCALAPPDATA || root,'AsiaAgent','requests.sqlite'));
  const inFlight=new Set();
  async function upstream(endpoint, { method = 'GET', data, signal } = {}) {
    const secret = JSON.parse(await readFile(config.secretPath, 'utf8'));
    const response = await fetch(config.upstream + endpoint, {
      method, headers: { Authorization: `Basic ${Buffer.from(`${secret.username}:${secret.password}`).toString('base64')}`, ...(data ? { 'Content-Type': 'application/json' } : {}) },
      body: data ? JSON.stringify(data) : undefined, signal: signal || AbortSignal.timeout(25000),
    });
    return response;
  }
  async function jsonUp(endpoint, options) {
    const res = await upstream(endpoint, options);
    if (!res.ok) {
      const raw = await res.text(); let detail = '';
      try { const e = JSON.parse(raw); detail = e.data?.message || e.message || e.name || ''; } catch {}
      throw Object.assign(new Error(res.status === 401 ? 'Connexion au serveur OpenCode refusée.' : `OpenCode (${res.status})${detail ? ': ' + detail.slice(0, 400) : ''}`), { status: res.status === 401 ? 502 : res.status });
    }
    return res.status === 204 ? null : res.json();
  }
  const dirQuery = dir => `directory=${encodeURIComponent(dir)}`;
  async function sessionEndpoint(id, suffix = '') {
    if (!/^ses_[a-zA-Z0-9]+$/.test(id)) throw Object.assign(new Error('Session invalide.'), { status: 400 });
    const session = await jsonUp(`/session/${id}`);
    return `/session/${id}${suffix}?${dirQuery(session.directory || config.directory)}`;
  }
  const server = http.createServer(async (req, res) => {
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.setHeader('Referrer-Policy', 'no-referrer');
    res.setHeader('X-Frame-Options', 'DENY');
    res.setHeader('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; font-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'");
    res.setHeader('Cache-Control', 'no-store');
    const send = (value, status = 200) => { res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8' }); res.end(JSON.stringify(value)); };
    try {
      if (!authorize(req, config)) return send({ error: 'Accès réservé à ton compte Tailscale.' }, 403);
      const url = new URL(req.url, 'http://local');
      const route = url.pathname;
      if (!['GET', 'HEAD'].includes(req.method) && !validMutation(req, csrf)) return send({ error: 'Recharge la page avant de réessayer.', code:'csrf_invalid' }, 403);
      if (req.method === 'GET' && route === '/api/bootstrap') {
        const health = await jsonUp('/global/health');
        return send({ csrf, healthy: health.healthy, version: health.version, name: 'Asia', model: config.model, profiles:config.profiles || [], limits:config.limits||null, defaultProfile:config.defaultProfile || 'pro', directory: config.directory, publicURL: `https://${config.publicHost}`, telegramURL: config.telegramURL || null });
      }
      if (req.method === 'GET' && route === '/api/routing') {
        let rows=[];
        if(config.metricsPath) { try { rows=(await readFile(config.metricsPath,'utf8')).trim().split('\n').filter(Boolean).flatMap(line=>{try{return [JSON.parse(line)]}catch{return []}}); } catch(error) { if(error.code!=='ENOENT')throw error; } }
        const totals={attempts:rows.length,success:0,errors:0,inputTokens:0,outputTokens:0,estimatedUSD:0,unpriced:0};
        for(const r of rows){if(r.status==='success')totals.success++;else totals.errors++;totals.inputTokens+=r.input_tokens||0;totals.outputTokens+=r.output_tokens||0;if(typeof r.cost_usd==='number')totals.estimatedUSD+=r.cost_usd;else totals.unpriced++;}
        const byModel=new Map();
        for(const r of rows){const key=r.model||r.routed_model||r.profile||'Inconnu';const m=byModel.get(key)||{model:key,calls:0,estimatedUSD:0};m.calls++;m.estimatedUSD+=typeof r.cost_usd==='number'?r.cost_usd:0;byModel.set(key,m);}
        return send({totals,models:[...byModel.values()],policy:config.routingPolicy||null,since:rows[0]?.time || null,profiles:config.profiles || []});
      }
      if (req.method === 'GET' && route === '/api/sessions') return send(await jsonUp('/session?limit=100&roots=true'));
      if (req.method === 'GET' && route === '/api/status') return send(await jsonUp(`/session/status?${dirQuery(config.directory)}`));
      if (req.method === 'POST' && route === '/api/sessions') {
        const data = await body(req);
        const profile = profileFor(config,data.profile);
        return send(await jsonUp(`/session?${dirQuery(config.directory)}`, { method: 'POST', data: { title: String(data.title || 'Nouvelle conversation').slice(0, 120), metadata:{asiaProfile:profile.id}, model: { providerID: profile.providerID, id: profile.modelID } } }));
      }
      if (req.method === 'GET' && route === '/api/events') {
        const controller = new AbortController(); res.on('close', () => controller.abort());
        const events = await upstream('/global/event', { signal: controller.signal });
        if (!events.ok) return send({ error: 'Flux indisponible.' }, 502);
        res.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache', 'Connection': 'keep-alive', 'X-Accel-Buffering': 'no' });
        res.flushHeaders(); const source = Readable.fromWeb(events.body); source.on('error', () => res.end()); source.pipe(res); return;
      }
      const match = route.match(/^\/api\/sessions\/(ses_[a-zA-Z0-9]+)\/(messages|prompt|abort|todos|diff|requests|profile)$/);
      if (match) {
        const [, id, action] = match;
        const session = await jsonUp(`/session/${id}`);
        const directory = session.directory || config.directory;
        const q = dirQuery(directory);
        if (req.method === 'POST' && action === 'profile') {
          const data=await body(req); const profile=profileFor(config,data.profile);
          if(journal.pending(`prompt:${id}`).length)return send({error:'Vérifie l’envoi en attente avant de changer de profil.'},409);
          const status=await jsonUp(`/session/status?${q}`);
          if(status[id] && status[id].type!=='idle')return send({error:'Attends la fin de la tâche avant de changer de profil.'},409);
          await jsonUp(`/session/${id}?${q}`,{method:'PATCH',data:{metadata:{...session.metadata,asiaProfile:profile.id}}});
          return send({profile:profile.id});
        }
        if (req.method === 'GET' && action === 'messages') return send(await jsonUp(`/session/${id}/message?${q}&limit=100`));
        if (req.method === 'GET' && action === 'todos') return send(await jsonUp(`/session/${id}/todo?${q}`));
        if (req.method === 'GET' && action === 'diff') return send(await jsonUp(`/session/${id}/diff?${q}`));
        if (req.method === 'GET' && action === 'requests') {
          const [permissions, questions, status] = await Promise.all([jsonUp(`/permission?${q}`), jsonUp(`/question?${q}`), jsonUp(`/session/status?${q}`)]);
          return send({ permissions: permissions.filter(p => p.sessionID === id), questions: questions.filter(p => p.sessionID === id), submissions:journal.pending(`prompt:${id}`),status: status[id] || { type: 'idle' }, profile:profileFor(config,session.metadata?.asiaProfile).id });
        }
        if (req.method === 'POST' && action === 'abort') return send(await jsonUp(await sessionEndpoint(id, '/abort'), { method: 'POST' }));
        if (req.method === 'POST' && action === 'prompt') {
          const data = await body(req);
          if(!validRequestId(data.requestId))return send({error:'Recharge la page : identifiant de demande manquant ou invalide.',code:'request_id_required'},400);
          if (typeof data.text !== 'string' || data.text.length > 50000 || !data.text.trim()) return send({ error: 'Écris un message (50 000 caractères maximum).' }, 400);
          const parts = [{ type: 'text', text: data.text }];
          if (data.attachments !== undefined && !Array.isArray(data.attachments)) return send({ error: 'Pièces jointes invalides.' }, 400);
          if ((data.attachments || []).length > 3) return send({ error: 'Trois pièces jointes maximum.' }, 400);
          for (const attachment of data.attachments || []) {
            if (!attachment || typeof attachment.text !== 'string' || attachment.text.length > 150000 || typeof attachment.name !== 'string') return send({ error: 'Fichier texte invalide ou trop volumineux.' }, 400);
            parts.push({ type: 'text', text: `Pièce jointe fournie par l’utilisateur : ${attachment.name.slice(0,150)}\n\n${attachment.text}\n\nFin de la pièce jointe.` });
          }
          const profile=profileFor(config,session.metadata?.asiaProfile);
          const scope=`prompt:${id}`,hash=fingerprint({parts,profile:profile.id});
          const previous=journal.get(data.requestId,scope,hash);
          if(previous){
            if(previous.state==='accepted'||previous.state==='rejected')return send(JSON.parse(previous.response),previous.status_code);
            if(inFlight.has(data.requestId))return send({error:'La demande est en cours de confirmation. Réessaie dans quelques instants.',code:'request_pending'},409);
            // Reconcile a lost acknowledgement using the deterministic upstream message ID.
            const check=await upstream(`/session/${id}/message/${previous.message_id}?${q}`);
            if(check.ok){const result={accepted:true,requestId:data.requestId,messageID:previous.message_id,reconciled:true};journal.finish(data.requestId,'accepted',result);return send(result);}
            if(check.status!==404)throw Object.assign(new Error('Vérification de la demande indisponible. Réessaie plus tard.'),{status:503,code:'request_pending'});
            return send({error:'Le résultat de cet envoi reste incertain. Il ne sera pas envoyé une seconde fois. Vérifie la conversation avant de poursuivre.',code:'request_uncertain'},409);
          }
          const currentStatus=await jsonUp(`/session/status?${q}`);
          if(currentStatus[id] && currentStatus[id].type!=='idle')return send({error:'Attends la fin de la tâche avant d’envoyer une autre demande.',code:'session_busy'},409);
          // Another handler may have reserved this ID while the status request was awaited.
          if(journal.get(data.requestId,scope,hash))return send({error:'La demande est déjà en cours de confirmation.',code:'request_pending'},409);
          const row=journal.begin(data.requestId,scope,hash);inFlight.add(data.requestId);
          try {
            const response=await upstream(`/session/${id}/prompt_async?${q}`,{method:'POST',data:{parts,messageID:row.message_id,model:{providerID:profile.providerID,modelID:profile.modelID}}});
            if(!response.ok){
              if(response.status>=400 && response.status<500 && response.status!==408){
                const result={error:`Demande refusée par OpenCode (${response.status}).`,code:'prompt_rejected',requestId:data.requestId};journal.finish(data.requestId,'rejected',result,response.status);return send(result,response.status);
              }
              throw new Error('Uncertain upstream response');
            }
            const result={accepted:true,requestId:data.requestId,messageID:row.message_id};journal.finish(data.requestId,'accepted',result);return send(result);
          } catch(error) {
            journal.uncertain(data.requestId);
            return send({error:'Confirmation interrompue. Réessaie le même message : son état sera vérifié avant tout nouvel envoi.',code:'request_uncertain',requestId:data.requestId},503);
          } finally {inFlight.delete(data.requestId);}
        }
      }
      const abandon=route.match(/^\/api\/sessions\/(ses_[a-zA-Z0-9]+)\/submissions\/([0-9a-f-]+)\/abandon$/i);
      if(abandon && req.method==='POST'){
        const [,id,requestId]=abandon;const data=await body(req);
        if(data.acknowledgePossibleDelivery!==true)return send({error:'Confirme la vérification de la conversation.'},400);
        const row=journal.lookup(requestId,`prompt:${id}`);if(!row)return send({error:'Demande inconnue.'},404);
        if(row.state==='accepted')return send({accepted:true});
        if(inFlight.has(requestId))return send({error:'Envoi encore en cours.',code:'request_pending'},409);
        const endpoint=await sessionEndpoint(id);const q=endpoint.split('?')[1];
        const status=await jsonUp(`/session/status?${q}`);
        if(status[id] && status[id].type!=='idle')return send({error:'Attends la fin de la tâche.'},409);
        const check=await upstream(`/session/${id}/message/${row.message_id}?${q}`);
        if(check.ok){const result={accepted:true,requestId,messageID:row.message_id,reconciled:true};journal.finish(requestId,'accepted',result);return send(result);}
        if(check.status!==404)return send({error:'Vérification indisponible. Réessaie plus tard.'},503);
        journal.finish(requestId,'rejected',{error:'Cet envoi a été abandonné sans être renvoyé.',code:'request_abandoned'},409);
        return send({abandoned:true});
      }
      const reply = route.match(/^\/api\/sessions\/(ses_[a-zA-Z0-9]+)\/(permission|question)\/(\w+)\/(reply|reject)$/);
      if (reply && req.method === 'POST') {
        const [, id, type, requestID, action] = reply;
        const session = await jsonUp(`/session/${id}`); const q = dirQuery(session.directory || config.directory);
        const pending = await jsonUp(`/${type}?${q}`);
        if (!pending.some(p => p.id === requestID && p.sessionID === id)) return send({ error: 'Cette demande n’est plus en attente.' }, 409);
        const data = await body(req);
        if (type === 'permission' && (action !== 'reply' || !['once','reject'].includes(data.reply))) return send({ error: 'Réponse invalide.' }, 400);
        if (type === 'question' && action === 'reply' && (!Array.isArray(data.answers) || !data.answers.every(a => Array.isArray(a) && a.every(s => typeof s === 'string')))) return send({ error: 'Réponse invalide.' }, 400);
        return send(await jsonUp(`/${type}/${requestID}/${action}?${q}`, { method: 'POST', data: type === 'permission' ? { reply: data.reply } : action === 'reply' ? { answers: data.answers } : {} }));
      }
      if (route.startsWith('/api/')) return send({ error: 'Route inconnue.' }, 404);
      if (!['GET','HEAD'].includes(req.method)) return send({ error: 'Méthode non autorisée.' }, 405);
      const assets = { '/': 'index.html', '/app.js': 'app.js', '/styles.css': 'styles.css', '/ui.css': 'ui.css', '/manifest.webmanifest': 'manifest.webmanifest', '/icon.svg': 'icon.svg', '/sw.js': 'sw.js', '/offline.html': 'offline.html' };
      const filename = assets[route]; if (!filename) return send({ error: 'Page introuvable.' }, 404);
      const types = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8', '.webmanifest': 'application/manifest+json', '.svg': 'image/svg+xml' };
      const file = await readFile(path.join(root, 'dist', filename));
      res.writeHead(200, { 'Content-Type': types[path.extname(filename)] }); res.end(req.method === 'HEAD' ? undefined : file);
    } catch (error) {
      if (res.headersSent) return res.end();
      const status = error.status || 502;
      send({ error: error.status ? error.message : 'Le serveur OpenCode est indisponible. Vérifie que le PC et OpenCode sont démarrés.',code:error.code }, status);
      if (!error.status) console.error(new Date().toISOString(), error.name, error.code || 'upstream-error');
    }
  });
  server.requestTimeout = 60000;
  server.on('close',()=>journal.close());
  return server;
}
if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const config = JSON.parse(await readFile(process.env.ASIA_CONFIG || path.join(root, 'config.local.json'), 'utf8'));
  createApp(config).listen(config.port, '127.0.0.1', () => console.log(`Asia ready on http://127.0.0.1:${config.port}`));
}
