import fs from 'node:fs';
import path from 'node:path';
import {createHash, randomUUID} from 'node:crypto';

const canonical = value => Array.isArray(value) ? value.map(canonical) : value && typeof value === 'object' ?
  Object.fromEntries(Object.keys(value).sort().map(key => [key,canonical(value[key])])) : value;
const digest = value => createHash('sha256').update(JSON.stringify(canonical(value))).digest('hex');
const id = value => {
  if (typeof value !== 'string' || !/^[a-zA-Z0-9_-]{8,100}$/.test(value)) throw Error('Identifiant invalide');
  return value;
};
const agents = Object.freeze({asia:'Asia', developpement:'Souleiman'});
export function assertBridgeAgent(context) {
  if (!Object.hasOwn(agents, context?.agentId)) throw Error('Agent non autorise sur la passerelle Windows');
  return context.agentId;
}
export function bridgeStateFile(base, agentId) {
  assertBridgeAgent({agentId});
  // Keep Asia's existing journal and receipts; new agents get separate stores.
  return path.join(base, 'asia-opencode', ...(agentId === 'asia' ? [] : [agentId]), 'tasks.json');
}

// Plugin hooks and tool factories may have separate module instances. A file
// lock serializes mutations; a crash lock fails closed for operator review.
// The journal is outside all workspaces and contains only sessions created here.
export class Bridge {
  constructor({stateFile, credentials, fetchImpl = fetch, agentId = 'asia'}) {
    this.agentId = assertBridgeAgent({agentId});
    this.stateFile = stateFile;
    this.credentials = credentials;
    this.fetch = fetchImpl;
    this.queue = Promise.resolve();
  }
  serial(fn) {
    const result = this.queue.then(async () => {
      fs.mkdirSync(path.dirname(this.stateFile), {recursive:true, mode:0o700});
      const lockPath = this.stateFile + '.lock';
      let lock;
      try { lock = fs.openSync(lockPath, 'wx', 0o600); }
      catch { throw Error('Passerelle occupee ou verrou apres incident : ne pas repeter une mutation incertaine'); }
      try {
        fs.writeFileSync(lock, JSON.stringify({pid:process.pid,createdAt:new Date().toISOString()}));
        return await fn();
      } finally { fs.closeSync(lock); fs.unlinkSync(lockPath); }
    });
    this.queue = result.catch(() => {});
    return result;
  }
  grantPath(callId) {
    if (typeof callId !== 'string' || !callId) throw Error('Identite de validation manquante');
    return path.join(path.dirname(this.stateFile),'approvals',digest(callId) + '.json');
  }
  load() {
    return fs.existsSync(this.stateFile) ? JSON.parse(fs.readFileSync(this.stateFile, 'utf8')) : {tasks:{}, requests:{}};
  }
  save(state) {
    fs.mkdirSync(path.dirname(this.stateFile), {recursive:true, mode:0o700});
    const temp = this.stateFile + '.tmp';
    fs.writeFileSync(temp, JSON.stringify(state), {mode:0o600});
    fs.renameSync(temp, this.stateFile);
  }
  own(taskId) {
    const task = this.load().tasks[id(taskId)];
    if (!task?.sessionId) throw Error('Tache inconnue ou creation incertaine : inspection operateur requise');
    if ((task.agentId ?? 'asia') !== this.agentId) throw Error('Tache appartenant a un autre agent');
    return task;
  }
  async request(route, body) {
    const auth = this.credentials();
    const url = new URL(route, 'http://host.docker.internal:4096');
    url.searchParams.set('directory', auth.directory);
    let response;
    try {
      response = await this.fetch(url, {
        method:body === undefined ? 'GET' : 'POST',
        headers:{Authorization:'Basic ' + Buffer.from(auth.username + ':' + auth.password).toString('base64'), 'Content-Type':'application/json'},
        body:body === undefined ? undefined : JSON.stringify(body), redirect:'error', signal:AbortSignal.timeout(20000),
      });
    } catch { throw Error('OpenCode indisponible ou resultat incertain ; ne pas relancer la meme action'); }
    if (!response.ok) throw Error('OpenCode HTTP ' + response.status);
    const text = await response.text();
    return text ? JSON.parse(text) : null;
  }
  async mutate(params) {
    return this.serial(async () => {
      const state = this.load();
      if (params.action === 'start' || params.action === 'continue') {
        const requestId = id(params.requestId);
        if (typeof params.prompt !== 'string' || !params.prompt.trim() || params.prompt.length > 12000) throw Error('Consigne manquante ou trop longue');
        const fingerprint = digest({action:params.action, taskId:params.taskId, prompt:params.prompt});
        if (state.requests[requestId]) {
          const previous = state.requests[requestId];
          if (previous.fingerprint !== fingerprint) throw Error('Identifiant deja utilise pour une autre consigne');
          return {taskId:previous.taskId, submission:previous.submission, repeated:true};
        }
        const taskId = params.action === 'start' ? randomUUID() : id(params.taskId);
        if (params.action === 'continue') this.own(taskId);
        state.requests[requestId] = {taskId, fingerprint, submission:'uncertain'};
        this.save(state); // Crash or timeout must never silently replay a side effect.
        if (params.action === 'start') {
          const created = await this.request('/session', {
            title:agents[this.agentId] + ' / ' + taskId, agent:'build',
            permission:[{permission:'read', pattern:'*AsiaDocker*', action:'deny'},
                        {permission:'edit', pattern:'*AsiaDocker*', action:'deny'}],
          });
          id(created.id);
          state.tasks[taskId] = {sessionId:created.id, agentId:this.agentId, createdAt:new Date().toISOString()};
          this.save(state);
        }
        const task = state.tasks[taskId];
        await this.request('/session/' + id(task.sessionId) + '/prompt_async', {
          model:{providerID:'litellm', modelID:'asia-auto'}, agent:'build',
          parts:[{type:'text', text:params.prompt}],
        });
        state.requests[requestId].submission = 'accepted';
        this.save(state);
        return {taskId, submission:'accepted', instruction:'Consulter status ; ne pas recreer cette tache.'};
      }
      const task = this.own(params.taskId);
      if (params.action === 'cancel') {
        await this.request('/session/' + id(task.sessionId) + '/abort', {});
        return {taskId:params.taskId, aborted:true};
      }
      if (params.action === 'reject') {
        await this.permission(params.taskId, params.permissionId);
        await this.request('/permission/' + id(params.permissionId) + '/reply', {reply:'reject'});
        return {rejected:true};
      }
      if (params.action === 'answer') {
        const questions = await this.request('/question');
        const question = questions.find(q => q.id === params.questionId && q.sessionID === task.sessionId);
        if (!question) throw Error('Question inconnue pour cette tache');
        if (!Array.isArray(params.answers) || params.answers.length !== question.questions.length ||
            params.answers.some(a => !Array.isArray(a) || a.some(v => typeof v !== 'string' || v.length > 4000))) throw Error('Reponses invalides');
        await this.request('/question/' + id(params.questionId) + '/reply', {answers:params.answers});
        return {answered:true};
      }
      throw Error('Action non prise en charge');
    });
  }
  async status(taskId) {
    const task = this.own(taskId), sessionId = id(task.sessionId);
    const [statuses, messages, permissions, questions] = await Promise.all([
      this.request('/session/status'), this.request('/session/' + sessionId + '/message?limit=6'),
      this.request('/permission'), this.request('/question'),
    ]);
    const last = [...messages].reverse().find(m => m.info?.role === 'assistant');
    return {
      taskId, status:statuses[sessionId]?.type || 'idle',
      completed:Boolean(last?.info?.time?.completed),
      text:(last?.parts || []).filter(p => p.type === 'text').map(p => p.text).join('\n').slice(-10000),
      tools:(last?.parts || []).filter(p => p.type === 'tool').map(p => ({tool:p.tool, status:p.state?.status})),
      permissions:permissions.filter(p => p.sessionID === sessionId).map(p => ({id:p.id, permission:p.permission, patterns:p.patterns})),
      questions:questions.filter(q => q.sessionID === sessionId).map(q => ({id:q.id, questions:q.questions})),
      error:last?.info?.error ? 'OpenCode a signale une erreur ; consulter sa tache.' : undefined,
    };
  }
  async permission(taskId, permissionId) {
    const task = this.own(taskId);
    const pending = await this.request('/permission');
    const request = pending.find(p => p.id === id(permissionId) && p.sessionID === task.sessionId);
    if (!request) throw Error('Autorisation absente ou appartenant a une autre tache');
    return request;
  }
  async approvalHook(event, context) {
    if (event.toolName !== 'asia_opencode_approve') return;
    try {
      if (assertBridgeAgent(context) !== this.agentId) throw Error('Validation reservee au proprietaire de la tache');
      if (!event.toolCallId) throw Error('Identite de l appel manquante');
      const params = structuredClone(event.params);
      const pending = await this.permission(params.taskId, params.permissionId);
      const description = pending.permission + ': ' + JSON.stringify(pending.patterns);
      // Never approve a command whose details were hidden by truncation.
      if (description.length > 470) throw Error('Demande trop longue : verifier dans OpenCode');
      return {requireApproval:{
        title:agents[this.agentId] + ' : autoriser cette action Windows une fois ?', description,
        severity:'warning', allowedDecisions:['allow-once','deny'], timeoutMs:120000,
        onResolution:decision => {
          // Hooks and tool factories can use distinct module instances. A private
          // single-use receipt bridges them; the model cannot write this folder.
          const filename = this.grantPath(event.toolCallId);
          if (decision !== 'allow-once') {fs.rmSync(filename,{force:true});return;}
          fs.mkdirSync(path.dirname(filename), {recursive:true,mode:0o700});
          fs.writeFileSync(filename, JSON.stringify({params:digest(params),pending:digest(pending),until:Date.now() + 30000}), {mode:0o600,flag:'wx'});
        },
      }};
    } catch (error) { return {block:true, blockReason:error.message}; }
  }
  async approve(callId, params) {
    return this.serial(async () => {
      const filename = this.grantPath(callId), consumed = filename + '.' + randomUUID() + '.consumed';
      try { fs.renameSync(filename,consumed); }
      catch { throw Error('Validation humaine native requise'); }
      let grant;
      try { grant = JSON.parse(fs.readFileSync(consumed,'utf8')); }
      finally { fs.unlinkSync(consumed); }
      if (!grant || grant.until < Date.now() || grant.params !== digest(params)) throw Error('Validation humaine native requise');
      const pending = await this.permission(params.taskId, params.permissionId);
      if (digest(pending) !== grant.pending) throw Error('La demande a change depuis sa validation');
      await this.request('/permission/' + id(params.permissionId) + '/reply', {reply:'once'});
      return {approvedOnce:true};
    });
  }
}
