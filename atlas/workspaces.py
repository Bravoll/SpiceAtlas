"""Named, independent database workspaces and an external manager registry."""
from __future__ import annotations
import contextlib,contextvars,json,os,shutil,sqlite3,threading,uuid
from pathlib import Path
from datetime import datetime,timezone
from .seed import ensure_baseline
ROOT=Path(__file__).resolve().parents[1]
DATA_ROOT=Path(os.environ.get('SPICE_DATA_DIR',ROOT/'data'))
def timestamp():return datetime.now(timezone.utc).isoformat(timespec='milliseconds')
class ClosingConnection(sqlite3.Connection):
    def __exit__(self,*args):
        try:return super().__exit__(*args)
        finally:self.close()
class Workspaces:
    def __init__(self,root=None,baseline=None):
        self.root=Path(root or DATA_ROOT);self.baseline=Path(baseline or self.root/'catalogue.sqlite3');self.registry=self.root/'versions.json';self.lock=threading.RLock();self.context=contextvars.ContextVar('atlas_version_'+uuid.uuid4().hex,default=None)
    def _write(self,value):
        self.root.mkdir(parents=True,exist_ok=True);tmp=self.registry.with_suffix('.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2),'utf-8');tmp.replace(self.registry)
    @staticmethod
    def backup(source,destination):
        source,destination=Path(source),Path(destination)
        if not source.exists():return
        destination.parent.mkdir(parents=True,exist_ok=True);src=sqlite3.connect(source,timeout=30);dst=sqlite3.connect(destination,timeout=30)
        try:
            src.backup(dst)
            try:dst.execute('PRAGMA journal_mode=DELETE')
            except sqlite3.OperationalError:pass
        finally:src.close();dst.close()
    def _read(self):
        with self.lock:
            if not self.registry.exists():
                key=uuid.uuid4().hex;folder=self.root/'versions'/key;folder.mkdir(parents=True)
                ensure_baseline(self.baseline)
                self.backup(self.baseline,folder/'catalogue.sqlite3');previous=ROOT/'config.local.json'
                if previous.exists() and self.root==DATA_ROOT:shutil.copy2(previous,folder/'config.local.json')
                now=timestamp();self._write({'schema':1,'active':key,'order':[key],'sort':'custom','direction':'asc','versions':[{'id':key,'name':'初始館藏 / Initial collection','created_at':now,'updated_at':now,'parent_id':None}],'deleted':[]})
                self.manager_event('version.initialize',{'id':key})
            return json.loads(self.registry.read_text('utf-8'))
    @property
    def active_id(self):return self._read()['active']
    @property
    def current_id(self):return self.context.get() or self.active_id
    def directory(self,key=None):
        key=key or self.current_id
        if not any(v['id']==key for v in self._read()['versions']):raise ValueError('Version not found')
        return self.root/'versions'/key
    @contextlib.contextmanager
    def use(self,key):
        self.directory(key);token=self.context.set(key)
        try:yield
        finally:self.context.reset(token)
    def manager_event(self,action,details):
        with self.lock:
            self.root.mkdir(parents=True,exist_ok=True)
            with (self.root/'version_manager.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps({'at':timestamp(),'action':action,'details':details},ensure_ascii=False)+'\n')
    def manager_logs(self,before=None,limit=100):
        path=self.root/'version_manager.jsonl'
        if not path.exists():return []
        from collections import deque
        with path.open(encoding='utf-8') as f:rows=deque(({'id':i,**json.loads(line)} for i,line in enumerate(f,1) if before is None or i<before),maxlen=min(200,limit))
        return list(reversed(rows))
    def touch(self,key=None):
        with self.lock:
            value=self._read();key=key or self.current_id
            for item in value['versions']:
                if item['id']==key:item['updated_at']=timestamp()
            self._write(value)
    def list(self):
        value=self._read();items=list(value['versions']);mode=value.get('sort','custom')
        if mode=='custom':
            order={k:i for i,k in enumerate(value['order'])};items.sort(key=lambda x:order.get(x['id'],99999))
        else:
            field={'created':'created_at','modified':'updated_at','name':'name'}[mode];items.sort(key=lambda x:(x[field].casefold(),x['id']),reverse=value.get('direction')=='desc')
        return {'active':value['active'],'versions':items,'sort':mode,'direction':value.get('direction','asc')}
    def create(self,name,mode='copy',source_id=None):
        name=str(name).strip()
        if not name or len(name)>100 or mode not in {'copy','default'}:raise ValueError('Choose a name (1–100 characters) and copy/default mode')
        with self.lock:
            value=self._read();source_id=source_id or value['active'];source=self.directory(source_id);key=uuid.uuid4().hex;folder=self.root/'versions'/key;folder.mkdir(parents=True)
            if mode=='copy':
                for file in source.iterdir():
                    if file.suffix=='.sqlite3':self.backup(file,folder/file.name)
                    elif file.name in {'config.local.json','view_state.json'}:shutil.copy2(file,folder/file.name)
                    elif file.is_dir() and file.name=='media':shutil.copytree(file,folder/file.name)
                with sqlite3.connect(folder/'catalogue.sqlite3',factory=ClosingConnection) as db:db.execute("UPDATE jobs SET status='paused' WHERE status IN ('queued','running')")
            else:
                ensure_baseline(self.baseline)
                self.backup(self.baseline,folder/'catalogue.sqlite3')
            now=timestamp();item={'id':key,'name':name,'created_at':now,'updated_at':now,'parent_id':source_id if mode=='copy' else None};value['versions'].append(item);value['order'].append(key);self._write(value);self.manager_event('version.create',{'id':key,'name':name,'mode':mode,'source_id':item['parent_id']});return item
    def switch(self,key):
        with self.lock:
            self.directory(key);value=self._read();old=value['active'];value['active']=key;self._write(value);self.manager_event('version.switch',{'from':old,'to':key})
    def rename(self,key,name):
        name=str(name).strip()
        if not name or len(name)>100:raise ValueError('Name must contain 1–100 characters')
        with self.lock:
            self.directory(key);value=self._read()
            for item in value['versions']:
                if item['id']==key:item.update(name=name,updated_at=timestamp())
            self._write(value);self.manager_event('version.rename',{'id':key,'name':name})
    def remove(self,key):
        with self.lock:
            value=self._read()
            if len(value['versions'])<=1:raise ValueError('Keep at least one version')
            folder=self.directory(key);trash=self.root/'version_trash'/key;trash.parent.mkdir(parents=True,exist_ok=True)
            try:folder.rename(trash);storage='trash'
            except PermissionError:storage='versions'
            item=next(v for v in value['versions'] if v['id']==key);value['deleted'].append({**item,'deleted_at':timestamp(),'storage':storage});value['versions']=[v for v in value['versions'] if v['id']!=key];value['order']=[x for x in value['order'] if x!=key]
            if value['active']==key:value['active']=value['versions'][0]['id']
            self._write(value);self.manager_event('version.delete',{'id':key,'recoverable':True});return value['active']
    def trash(self):return self._read().get('deleted',[])
    def restore(self,key):
        with self.lock:
            value=self._read();item=next((v for v in value['deleted'] if v['id']==key),None)
            if not item:raise ValueError('Deleted version not found')
            if item.get('storage','trash')=='trash':(self.root/'version_trash'/key).rename(self.root/'versions'/key)
            item={k:v for k,v in item.items() if k not in {'deleted_at','storage'}};item['updated_at']=timestamp();value['deleted']=[v for v in value['deleted'] if v['id']!=key];value['versions'].append(item);value['order'].append(key);self._write(value);self.manager_event('version.restore',{'id':key});return item
    def reorder(self,order=None,sort=None,direction='asc'):
        with self.lock:
            value=self._read()
            if order is not None:
                if len(order)!=len(set(order)) or set(order)!={v['id'] for v in value['versions']}:raise ValueError('Order must include each version exactly once')
                value['order']=order;value['sort']='custom'
            elif sort in {'custom','created','modified','name'} and direction in {'asc','desc'}:value['sort']=sort;value['direction']=direction
            else:raise ValueError('Unsupported ordering')
            self._write(value);self.manager_event('version.order',{'order':value['order'],'sort':value['sort'],'direction':value['direction']});return self.list()
workspaces=Workspaces()
