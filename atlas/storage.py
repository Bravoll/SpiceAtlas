from __future__ import annotations
import json,os,sqlite3,time
from pathlib import Path
from .workspaces import workspaces,ClosingConnection
from .cache_memory import CACHE_MODE,memory_cache
ROOT=Path(__file__).resolve().parents[1]
DATA=Path(os.environ.get('SPICE_DATA_DIR',ROOT/'data'))
MEDIA=DATA/'media'  # legacy import only; runtime media is version-local

def media_root():
 path=workspaces.directory()/'media';path.mkdir(exist_ok=True);return path

def now_iso():
 from datetime import datetime,timezone
 return datetime.now(timezone.utc).isoformat(timespec='seconds')
class Store:
 def __init__(self,path=None):self._path=Path(path) if path else None
 @property
 def path(self):return self._path or workspaces.directory()/'cache.sqlite3'
 def connect(self):
  self.path.parent.mkdir(parents=True,exist_ok=True);db=sqlite3.connect(self.path,timeout=20,factory=ClosingConnection)
  db.execute('CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY,payload TEXT NOT NULL,saved REAL NOT NULL,expires REAL NOT NULL)')
  db.execute('CREATE TABLE IF NOT EXISTS retention(key TEXT PRIMARY KEY,reason TEXT NOT NULL,at REAL NOT NULL)');return db
 @property
 def namespace(self):return str(self.path.resolve())
 def get(self,key):
  value=memory_cache.get(self.namespace,key)
  if value is not None:return {'value':value,'stale':False,'tier':'memory'}
  with self.connect() as db:row=db.execute('SELECT c.payload,c.expires,r.reason,c.saved FROM cache c LEFT JOIN retention r ON r.key=c.key WHERE c.key=?',(key,)).fetchone()
  return {'value':json.loads(row[0]),'stale':False if row[2] else row[1]<time.time(),'tier':'retained' if row[2] else 'disk','retention_reason':row[2],'saved_at':row[3]} if row else None
 def retain(self,key,reason='frequent'):
  with self.connect() as db:db.execute('INSERT OR REPLACE INTO retention VALUES(?,?,?)',(key,reason,time.time()))
  value=memory_cache.get(self.namespace,key)
  if value is not None:
   token=CACHE_MODE.set('longterm')
   try:self.put(key,value)
   finally:CACHE_MODE.reset(token)
 def put(self,key,value,ttl=604800):
  if CACHE_MODE.get()=='memory':memory_cache.put(self.namespace,key,value,min(ttl,1800));return
  with self.connect() as db:
   db.execute('INSERT OR REPLACE INTO cache VALUES(?,?,?,?)',(key,json.dumps(value,ensure_ascii=False),time.time(),time.time()+ttl))
   if CACHE_MODE.get()=='longterm':db.execute('INSERT OR IGNORE INTO retention VALUES(?,?,?)',(key,'first_page_or_favorite',time.time()))
  memory_cache.discard(self.namespace,key)
 def snapshot(self,key):
  path=ROOT/'data/snapshots'/(key.replace(':','--')+'.json');return json.loads(path.read_text('utf-8')) if path.is_file() else None
 def stats(self):
  with self.connect() as db:n=db.execute('SELECT COUNT(*) FROM cache').fetchone()[0]
  return {'cached_records':n}
