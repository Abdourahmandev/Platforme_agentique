"""Encrypted snapshots. Restore checks only ever extract to a private staging folder."""
import argparse,hashlib,json,os,secrets,shutil,sqlite3,stat,subprocess,tempfile,zipfile
from datetime import datetime,timezone
from pathlib import Path
from contextlib import closing
from cryptography.hazmat.primitives.ciphers import Cipher,algorithms,modes

APP=Path(__file__).resolve().parents[1];HOME=Path.home();LOCAL=Path(os.environ.get('LOCALAPPDATA') or HOME/'.local/share')
STATE=LOCAL/'AsiaBackup';DEST=Path(os.environ.get('ASIA_BACKUP_DIR') or ('D:/AsiaBackups' if os.name=='nt' else LOCAL/'AsiaBackups'));PG=LOCAL/'Programs/AsiaPostgreSQL/pgsql/bin'
EXCLUDE={'node_modules','venv','__pycache__','.playwright-mcp','dist','.git'}
def private(path):
 path.mkdir(parents=True,exist_ok=True)
 if os.name!='nt':path.chmod(0o700);return
 who=subprocess.check_output(['whoami'],text=True).strip()
 subprocess.run(['icacls',str(path),'/inheritance:r','/grant:r',who+':(OI)(CI)F','*S-1-5-18:(OI)(CI)F'],check=True,stdout=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
def pg(args,**kwargs):
 creds=json.loads((LOCAL/'AsiaPostgreSQL/credentials.json').read_text())
 env=dict(os.environ,PGPASSWORD=creds['admin'])
 r=subprocess.run([str(PG/args[0]),*args[1:]],env=env,capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW,**kwargs)
 if r.returncode:raise RuntimeError('PostgreSQL backup/restore command failed (details withheld to protect credentials).')
 return r.stdout
PGCON=['-h','127.0.0.1','-p','55432','-U','postgres']
def safe_remove(path):
 if path.resolve().parent!=STATE.resolve() or not path.name.startswith('stage-'):raise RuntimeError('Unsafe cleanup path')
 def writable_retry(function,name,error):
  if not isinstance(error,PermissionError):raise error
  candidate=Path(name)
  if not candidate.resolve().is_relative_to(path.resolve()):raise RuntimeError('Unsafe cleanup entry')
  candidate.chmod(stat.S_IWRITE|stat.S_IREAD)
  function(name)
 shutil.rmtree(path,onexc=writable_retry)
def key(create=False):
 p=STATE/'recovery-key.txt'
 if not p.exists():
  if not create:raise RuntimeError('Recovery key missing; refusing to replace it.')
  fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
  with os.fdopen(fd,'w',encoding='ascii') as f:f.write(secrets.token_hex(32))
 return bytes.fromhex(p.read_text().strip())
def encrypt(source,target):
 nonce=secrets.token_bytes(12);enc=Cipher(algorithms.AES(key()),modes.GCM(nonce)).encryptor()
 with source.open('rb') as src,target.open('wb') as dst:
  dst.write(b'ASIA1'+nonce)
  while block:=src.read(1024*1024):dst.write(enc.update(block))
  dst.write(enc.finalize());dst.write(enc.tag)
def decrypt(source,target):
 # Never retain unauthenticated plaintext, including on a truncated archive.
 if target.exists():raise FileExistsError('Restore destination already exists')
 created=False
 try:
  with source.open('rb') as src:
   size=os.fstat(src.fileno()).st_size
   if size<33 or src.read(5)!=b'ASIA1':raise ValueError('Invalid archive header')
   nonce=src.read(12);src.seek(-16,2);tag=src.read(16);remaining=size-33;src.seek(17)
   dec=Cipher(algorithms.AES(key()),modes.GCM(nonce,tag)).decryptor()
   with target.open('xb') as dst:
    created=True
    while remaining>0:
     block=src.read(min(1024*1024,remaining))
     if not block:raise ValueError('Truncated archive')
     remaining-=len(block);dst.write(dec.update(block))
    dst.write(dec.finalize())
 except BaseException:
  if created:target.unlink(missing_ok=True)
  raise
def sources():
 return {'app':APP,'workspace':HOME/'Documents/OpenCode','opencode-config':HOME/'.config/opencode','openchamber-config':HOME/'.config/openchamber','telegram-settings':Path(os.environ['APPDATA'])/'opencode-telegram-bot','telegram-secrets':LOCAL/'OpenCodeTelegramSetup','opencode-service':LOCAL/'OpenCodeWeb','openchamber-service':LOCAL/'OpenChamberWeb','gateway-secrets':LOCAL/'AsiaLiteLLM','speech-code':LOCAL/'Programs/OpenCodeTelegramSpeech','telegram-code':LOCAL/'Programs/OpenCodeTelegram','google-oauth':HOME/'.google_workspace_mcp'}
def snapshot(stage):
 files={};roots=sources()
 for label,folder in roots.items():
  if not folder.exists():continue
  for base,dirs,names in os.walk(folder):
   dirs[:]=[d for d in dirs if d not in EXCLUDE and not d.startswith('model-') and not (Path(base)/d).is_symlink()]
   for name in names:
    p=Path(base)/name
    if p.is_symlink() or p.suffix.lower() in {'.log','.zip','.tgz','.lock','.exe','.dll','.pyc'} or name.endswith('runtime.json'):continue
    rel=Path(label)/p.relative_to(folder);target=stage/'files'/rel;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target);files[str(rel)]=hashlib.sha256(target.read_bytes()).hexdigest()
 db=stage/'files/opencode-data/opencode.db';db.parent.mkdir(parents=True,exist_ok=True)
 with closing(sqlite3.connect('file:'+str(HOME/'.local/share/opencode/opencode.db')+'?mode=ro',uri=True)) as src,closing(sqlite3.connect(db)) as dst:src.backup(dst)
 auth=HOME/'.local/share/opencode/auth.json';shutil.copy2(auth,db.parent/'auth.json')
 journal=LOCAL/'AsiaAgent/requests.sqlite'
 if journal.exists():
  target=stage/'files/asia-data/requests.sqlite';target.parent.mkdir(parents=True,exist_ok=True)
  with closing(sqlite3.connect('file:'+str(journal)+'?mode=ro',uri=True)) as src,closing(sqlite3.connect(target)) as dst:src.backup(dst)
 pg(['pg_dump.exe',*PGCON,'-d','litellm','-Fc','-f',str(stage/'files/litellm.dump')])
 for p in [LOCAL/'AsiaPostgreSQL/credentials.json',LOCAL/'AsiaPostgreSQL/data/postgresql.conf',LOCAL/'AsiaPostgreSQL/data/pg_hba.conf']:
  target=stage/'files/postgres-config'/p.name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
 with closing(sqlite3.connect(db)) as con:count=con.execute('SELECT count(*) FROM session').fetchone()[0]
 files={str(p.relative_to(stage/'files')):hashlib.sha256(p.read_bytes()).hexdigest() for p in (stage/'files').rglob('*') if p.is_file()}
 manifest={'version':1,'created_at':datetime.now(timezone.utc).isoformat(),'sqlite_sessions':count,'files':files,'source_roots':{k:str(v) for k,v in roots.items()},'excluded':'Installed runtimes, dependencies, browser caches, logs and downloaded speech models; reinstall from manifests. OpenCode snapshot/repo caches excluded.'}
 (stage/'files/manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
 return manifest
def verify(archive,restore=False):
 stage=Path(tempfile.mkdtemp(prefix='stage-',dir=STATE))
 try:
  decrypt(archive,stage/'archive.zip')
  with zipfile.ZipFile(stage/'archive.zip') as z:
   for member in z.namelist():
    if not (stage/'restore'/member).resolve().is_relative_to((stage/'restore').resolve()):raise ValueError('Unsafe archive entry')
   z.extractall(stage/'restore')
  base=stage/'restore';manifest=json.loads((base/'manifest.json').read_text())
  for rel,digest in manifest['files'].items():
   if not (base/rel).resolve().is_relative_to(base.resolve()):raise ValueError('Unsafe manifest entry')
   if hashlib.sha256((base/rel).read_bytes()).hexdigest()!=digest:raise ValueError('Snapshot hash mismatch')
  with closing(sqlite3.connect(base/'opencode-data/opencode.db')) as con:
   if con.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('SQLite integrity failure')
   if con.execute('SELECT count(*) FROM session').fetchone()[0]!=manifest['sqlite_sessions']:raise ValueError('SQLite session count mismatch')
  pg(['pg_restore.exe','--list',str(base/'litellm.dump')])
  result={'archive':str(archive),'files_verified':len(manifest['files']),'sqlite_sessions':manifest['sqlite_sessions'],'sqlite_integrity':'ok','postgres_dump_readable':True,'postgres_restored':False}
  if restore:
   dbname='asia_restore_check_'+secrets.token_hex(6)
   pg(['createdb.exe',*PGCON,dbname])
   try:
    pg(['pg_restore.exe',*PGCON,'-d',dbname,'--no-owner','--no-privileges','--exit-on-error',str(base/'litellm.dump')])
    count=int(pg(['psql.exe',*PGCON,'-d',dbname,'-Atc',"SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"]).strip())
    if count<80:raise ValueError('Incomplete PostgreSQL restore')
    result.update(postgres_restored=True,postgres_tables=count)
   finally:pg(['dropdb.exe',*PGCON,dbname])
  return result
 finally:safe_remove(stage)
def create():
 private(STATE);private(DEST);key(create=True);stage=Path(tempfile.mkdtemp(prefix='stage-',dir=STATE))
 try:
  manifest=snapshot(stage);shutil.make_archive(str(stage/'archive'),'zip',stage/'files')
  archive=DEST/(datetime.now(timezone.utc).strftime('asia-%Y%m%dT%H%M%S-')+secrets.token_hex(3)+'.aes')
  temp=archive.with_suffix('.partial');encrypt(stage/'archive.zip',temp);temp.replace(archive)
  result=verify(archive);(STATE/'last-backup.json').write_text(json.dumps(result|{'completed_at':datetime.now(timezone.utc).isoformat()},indent=2))
  return result
 finally:safe_remove(stage)
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--verify',type=Path);parser.add_argument('--restore-check',action='store_true');args=parser.parse_args()
 private(STATE)
 result=verify(args.verify,args.restore_check) if args.verify else create()
 if args.restore_check and not args.verify:result=verify(Path(result['archive']),True)
 print(json.dumps(result))
