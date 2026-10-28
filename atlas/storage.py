from __future__ import annotations
import json,os,sqlite3,time
from pathlib import Path
from .workspaces import workspaces,ClosingConnection
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
  db.execute('CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY,payload TEXT NOT NULL,saved REAL NOT NULL,expires REAL NOT NULL)');return db
 def get(self,key):
  with self.connect() as db:row=db.execute('SELECT payload,expires FROM cache WHERE key=?',(key,)).fetchone()
  return {'value':json.loads(row[0]),'stale':row[1]<time.time()} if row else None
 def put(self,key,value,ttl=604800):
  with self.connect() as db:db.execute('INSERT OR REPLACE INTO cache VALUES(?,?,?,?)',(key,json.dumps(value,ensure_ascii=False),time.time(),time.time()+ttl))
 def snapshot(self,key):
  path=ROOT/'data/snapshots'/(key.replace(':','--')+'.json');return json.loads(path.read_text('utf-8')) if path.is_file() else None
 def stats(self):
  with self.connect() as db:n=db.execute('SELECT COUNT(*) FROM cache').fetchone()[0]
  return {'cached_records':n}
