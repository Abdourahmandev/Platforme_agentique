import pg from 'pg';
import {Problem,newJob,hash} from './core.mjs';
export class Store{
  constructor(connectionString){this.pool=new pg.Pool({connectionString,max:5,connectionTimeoutMillis:5000});}
  async init(){await this.pool.query(`CREATE TABLE IF NOT EXISTS jobs (
    id uuid PRIMARY KEY, actor text NOT NULL, request_id text NOT NULL, input_hash text NOT NULL,
    job jsonb NOT NULL, cancel_requested boolean NOT NULL DEFAULT false, created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(), UNIQUE(actor,request_id));
    CREATE TABLE IF NOT EXISTS events (seq bigserial PRIMARY KEY, job_id uuid REFERENCES jobs(id), event text NOT NULL, details jsonb NOT NULL DEFAULT '{}', at timestamptz NOT NULL DEFAULT now());
    CREATE TABLE IF NOT EXISTS outbox (id bigserial PRIMARY KEY, job_id uuid REFERENCES jobs(id), kind text NOT NULL, state text NOT NULL DEFAULT 'pending', message_id bigint, UNIQUE(job_id,kind));`);}
  async get(id){if(!/^[a-f0-9-]{36}$/.test(id||''))throw new Problem('Identifiant invalide');const r=await this.pool.query('SELECT job,cancel_requested FROM jobs WHERE id=$1',[id]);if(!r.rowCount)throw new Problem('Publication introuvable');return {...r.rows[0].job,cancelRequested:r.rows[0].cancel_requested};}
  async existing(actor,input){const r=await this.pool.query('SELECT job,input_hash FROM jobs WHERE actor=$1 AND request_id=$2',[actor,input.requestId]);if(!r.rowCount)return null;if(r.rows[0].input_hash!==hash(JSON.stringify(input)))throw new Problem('requestId reutilise avec un contenu different');return r.rows[0].job;}
  async create(actor,input,base){
    const j=newJob(input,base),c=await this.pool.connect();
    try{await c.query('BEGIN');const r=await c.query('INSERT INTO jobs(id,actor,request_id,input_hash,job) VALUES($1,$2,$3,$4,$5) ON CONFLICT(actor,request_id) DO NOTHING RETURNING id',[j.id,actor,input.requestId,hash(JSON.stringify(input)),j]);
      if(!r.rowCount){await c.query('ROLLBACK');return this.existing(actor,input);}
      await c.query("INSERT INTO events(job_id,event) VALUES($1,'prepared')",[j.id]);
      for(const kind of ['review','awaiting_approval'])await c.query('INSERT INTO outbox(job_id,kind) VALUES($1,$2)',[j.id,kind]);
      await c.query('COMMIT');return j;
    }catch(e){await c.query('ROLLBACK');throw e;}finally{c.release();}
  }
  async enqueue(id,kind){await this.pool.query('INSERT INTO outbox(job_id,kind) VALUES($1,$2) ON CONFLICT DO NOTHING',[id,kind]);}
  async decide(id,digest,action,actor){
    const c=await this.pool.connect();try{await c.query('BEGIN');const r=await c.query('SELECT job,cancel_requested FROM jobs WHERE id=$1 FOR UPDATE',[id]);if(!r.rowCount)throw new Problem('Publication introuvable');const j=r.rows[0].job;
      if(digest!==j.digest&&digest!==j.digest.slice(0,12))throw new Problem('Empreinte differente');
      if(action==='approve'){
        if(r.rows[0].cancel_requested)throw new Problem('Publication annulee');
        if(['queued','working','published'].includes(j.state)){await c.query('ROLLBACK');return j;}
        if(j.state!=='awaiting_approval')throw new Problem('Publication non approuvable');
        if(Date.parse(j.expiresAt)<Date.now()){j.state='expired';j.error='Validation expiree';}else{j.state='queued';j.approval={actor,at:new Date().toISOString(),digest:j.digest};}
      }else if(action==='deny'){
        if(j.state!=='awaiting_approval')throw new Problem('Refus reserve a une demande en attente');j.state='denied';
      }else if(action==='cancel'){
        if(j.state==='published')throw new Problem('Publication deja terminee ; PR conservee');
        await c.query('UPDATE jobs SET cancel_requested=true WHERE id=$1',[id]);
        if(j.state==='uncertain')j.state='queued';
        else if(!['working','queued'].includes(j.state))j.state='cancelled';
      }else if(action==='reconcile'){
        if(j.state!=='uncertain'||r.rows[0].cancel_requested)throw new Problem('Reconciliation reservee a une publication incertaine non annulee');
        j.state='queued';j.error=null;
      }else throw new Problem('Decision inconnue');
      await c.query('UPDATE jobs SET job=$2,updated_at=now() WHERE id=$1',[id,j]);
      await c.query('INSERT INTO events(job_id,event,details) VALUES($1,$2,$3)',[id,action,{actor,digest:j.digest}]);
      await c.query('INSERT INTO outbox(job_id,kind) VALUES($1,$2) ON CONFLICT DO NOTHING',[id,j.state]);
      await c.query('COMMIT');return j;
    }catch(e){await c.query('ROLLBACK');throw e;}finally{c.release();}
  }
  async locked(id,fn){
    const c=await this.pool.connect();let alive=true;c.on('error',()=>{alive=false;});
    try{if(!(await c.query('SELECT pg_try_advisory_lock(hashtext($1)) AS ok',[id])).rows[0].ok)return;
      const r=await c.query('SELECT job,cancel_requested FROM jobs WHERE id=$1',[id]);const j=r.rows[0].job;
      if(!['queued','working'].includes(j.state))return;
      j.state='working';
      const save=async job=>{if(!alive)throw new Problem('Verrou perdu','uncertain');await c.query('UPDATE jobs SET job=$2,updated_at=now() WHERE id=$1',[id,job]);};
      await save(j);
      await fn(j,{save,cancelled:async()=>{if(!alive)throw new Problem('Verrou perdu','uncertain');return (await c.query('SELECT cancel_requested FROM jobs WHERE id=$1',[id])).rows[0].cancel_requested;},notify:async job=>this.enqueue(id,job.state)});
    }finally{if(alive)await c.query('SELECT pg_advisory_unlock(hashtext($1))',[id]);c.release(!alive);}
  }
  async pending(){
    await this.pool.query("UPDATE jobs SET job=jsonb_set(job,'{state}','\"expired\"') WHERE job->>'state'='awaiting_approval' AND (job->>'expiresAt')::timestamptz < now()");
    // Recover missed outbox inserts after a crash between saving state and enqueueing.
    await this.pool.query("INSERT INTO outbox(job_id,kind) SELECT id,job->>'state' FROM jobs WHERE job->>'state' IN ('awaiting_approval','published','cancelled','denied','expired','blocked','uncertain') ON CONFLICT DO NOTHING");
    return (await this.pool.query("SELECT id FROM jobs WHERE job->>'state' IN ('queued','working') ORDER BY created_at LIMIT 20")).rows;
  }
  async nextNotification(){return (await this.pool.query("UPDATE outbox SET state='sending' WHERE id=(SELECT id FROM outbox WHERE state='pending' ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 1) RETURNING *")).rows[0];}
  async notificationDone(id,messageId){await this.pool.query("UPDATE outbox SET state='sent',message_id=$2 WHERE id=$1",[id,messageId]);}
  async notificationUncertain(id){await this.pool.query("UPDATE outbox SET state='uncertain' WHERE id=$1",[id]);}
}
