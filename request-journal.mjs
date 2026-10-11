import { DatabaseSync } from 'node:sqlite';
import { mkdirSync } from 'node:fs';
import path from 'node:path';
import { createHash, randomBytes } from 'node:crypto';

export const fingerprint = value => createHash('sha256').update(JSON.stringify(value)).digest('hex');
export const validRequestId = value => typeof value === 'string' && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);
export class RequestJournal {
  constructor(filename) {
    mkdirSync(path.dirname(filename), { recursive:true });
    this.db=new DatabaseSync(filename);
    this.db.exec(`PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL; PRAGMA busy_timeout=5000;
      CREATE TABLE IF NOT EXISTS requests (
        id TEXT PRIMARY KEY, scope TEXT NOT NULL, fingerprint TEXT NOT NULL,
        state TEXT NOT NULL, message_id TEXT, response TEXT, status_code INTEGER,
        created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL);
      CREATE UNIQUE INDEX IF NOT EXISTS pending_scope ON requests(scope) WHERE state IN ('pending','uncertain');`);
    // An interrupted submission may already have reached OpenCode. Never replay it blindly.
    this.db.prepare("UPDATE requests SET state='uncertain' WHERE state='pending'").run();
  }
  get(id,scope,hash) {
    const row=this.db.prepare('SELECT * FROM requests WHERE id=?').get(id);
    if(row && (row.scope!==scope || row.fingerprint!==hash))throw Object.assign(new Error('Cet identifiant appartient à une autre demande.'),{status:409,code:'request_conflict'});
    return row;
  }
  begin(id,scope,hash) {
    const existing=this.get(id,scope,hash);if(existing)return existing;
    const blocked=this.db.prepare("SELECT id FROM requests WHERE scope=? AND state IN ('pending','uncertain')").get(scope);
    if(blocked)throw Object.assign(new Error('Une demande est encore en cours de confirmation. Réessaie la demande initiale.'),{status:409,code:'request_pending'});
    const messageID='msg_'+Date.now().toString(16)+randomBytes(10).toString('hex');
    this.db.prepare("INSERT INTO requests(id,scope,fingerprint,state,message_id,created_at,updated_at) VALUES(?,?,?,'pending',?,?,?)").run(id,scope,hash,messageID,Date.now(),Date.now());
    return this.get(id,scope,hash);
  }
  finish(id,state,response,status=200) {
    this.db.prepare('UPDATE requests SET state=?,response=?,status_code=?,updated_at=? WHERE id=?').run(state,JSON.stringify(response),status,Date.now(),id);
  }
  uncertain(id) {this.db.prepare("UPDATE requests SET state='uncertain',updated_at=? WHERE id=?").run(Date.now(),id);}
  pending(scope){return this.db.prepare("SELECT id,state,updated_at FROM requests WHERE scope=? AND state IN ('pending','uncertain')").all(scope);}
  lookup(id,scope){return this.db.prepare('SELECT * FROM requests WHERE id=? AND scope=?').get(id,scope);}
  close(){this.db.close();}
}
