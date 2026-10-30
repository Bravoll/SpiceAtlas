"""Version-local logs, collections and manually dismissed service notices."""
import json,sqlite3,uuid
from .workspaces import timestamp,workspaces,ClosingConnection
from .runtime import event
class Activity:
    def connect(self):
        db=sqlite3.connect(workspaces.directory()/'activity.sqlite3',timeout=30,factory=ClosingConnection);db.row_factory=sqlite3.Row
        db.executescript('''PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,at TEXT,action TEXT,details TEXT,severity TEXT);
        CREATE TABLE IF NOT EXISTS favorites(entry_id TEXT PRIMARY KEY,added_at TEXT,position INTEGER,note TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS history(entry_id TEXT PRIMARY KEY,visited_at TEXT,visits INTEGER,position INTEGER);
        CREATE TABLE IF NOT EXISTS notifications(id TEXT PRIMARY KEY,created_at TEXT,title TEXT,details TEXT,dismissed INTEGER DEFAULT 0);''');return db
    def log(self,action,details=None,severity='info'):
        with self.connect() as db:db.execute('INSERT INTO events(at,action,details,severity) VALUES(?,?,?,?)',(timestamp(),action,json.dumps(details or {},ensure_ascii=False),severity))
        workspaces.touch()
        event(action,details=details or {},version=workspaces.current_id)
    def events(self,before=None,limit=100):
        with self.connect() as db:rows=db.execute('SELECT * FROM events WHERE (? IS NULL OR id<?) ORDER BY id DESC LIMIT ?',(before,before,min(200,max(1,limit)))).fetchall()
        return [{**dict(r),'details':json.loads(r['details'])} for r in rows]
    def visit(self,key):
        with self.connect() as db:db.execute('INSERT INTO history VALUES(?,?,1,(SELECT COALESCE(MAX(position),-1)+1 FROM history)) ON CONFLICT(entry_id) DO UPDATE SET visited_at=excluded.visited_at,visits=history.visits+1',(key,timestamp()))
        self.log('history.visit',{'entry_id':key})
    def favorite(self,key,enabled=True,note=''):
        with self.connect() as db:
            if enabled:db.execute('INSERT INTO favorites VALUES(?,?,(SELECT COALESCE(MAX(position),-1)+1 FROM favorites),?) ON CONFLICT(entry_id) DO UPDATE SET note=excluded.note',(key,timestamp(),note[:1000]))
            else:db.execute('DELETE FROM favorites WHERE entry_id=?',(key,))
        self.log('favorite.add' if enabled else 'favorite.remove',{'entry_id':key})
    def collection(self,kind,custom=False):
        if kind not in {'favorites','history'}:raise ValueError('Unknown collection')
        with self.connect() as db:return [dict(r) for r in db.execute('SELECT * FROM '+kind+' ORDER BY '+('position' if kind=='favorites' or custom else 'visited_at DESC'))]
    def reorder(self,kind,order):
        if kind not in {'favorites','history'}:raise ValueError('Unknown collection')
        with self.connect() as db:
            keys={r[0] for r in db.execute('SELECT entry_id FROM '+kind)}
            if len(order)!=len(set(order)) or set(order)!=keys:raise ValueError('Order must contain every stored entry')
            db.executemany('UPDATE '+kind+' SET position=? WHERE entry_id=?',[(i,k) for i,k in enumerate(order)])
        self.log(kind+'.order',{'order':order})
    def notify(self,title,details):
        key=uuid.uuid4().hex
        with self.connect() as db:db.execute('INSERT INTO notifications VALUES(?,?,?,?,0)',(key,timestamp(),title,json.dumps(details,ensure_ascii=False)))
        return key
    def notifications(self):
        with self.connect() as db:return [{**dict(r),'details':json.loads(r['details'])} for r in db.execute('SELECT * FROM notifications WHERE dismissed=0 ORDER BY created_at DESC LIMIT 100')]
    def update_notification(self,key,title,details):
        with self.connect() as db:db.execute('UPDATE notifications SET title=?,details=? WHERE id=?',(title,json.dumps(details,ensure_ascii=False),key))
    def dismiss(self,key):
        with self.connect() as db:db.execute('UPDATE notifications SET dismissed=1 WHERE id=?',(key,))
activity=Activity()
