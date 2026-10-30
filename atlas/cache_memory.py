"""Bounded, version/path-isolated speculative memory; never persisted by prediction."""
from __future__ import annotations
import contextvars,json,threading,time
from collections import OrderedDict

CACHE_MODE=contextvars.ContextVar('atlas_cache_mode',default='foreground')
class MemoryCache:
    def __init__(self,max_bytes=64*1024*1024,namespace_bytes=32*1024*1024):
        self.max_bytes=max_bytes;self.namespace_bytes=namespace_bytes;self.values=OrderedDict();self.bytes=0;self.lock=threading.RLock()
    def put(self,namespace,key,value,ttl=900):
        payload=json.dumps(value,ensure_ascii=False);size=len(payload.encode('utf-8'))
        if size>self.namespace_bytes:return False
        with self.lock:
            self._remove((namespace,key));self.values[(namespace,key)]=(payload,time.time()+ttl,size);self.bytes+=size
            while self.bytes>self.max_bytes or sum(v[2] for k,v in self.values.items() if k[0]==namespace)>self.namespace_bytes:
                victim=next((k for k in self.values if k[0]==namespace),next(iter(self.values))) if self.bytes<=self.max_bytes else next(iter(self.values))
                self._remove(victim)
        return True
    def _remove(self,key):
        row=self.values.pop(key,None)
        if row:self.bytes-=row[2]
    def get(self,namespace,key):
        with self.lock:
            row=self.values.get((namespace,key))
            if not row:return None
            if row[1]<time.time():self._remove((namespace,key));return None
            self.values.move_to_end((namespace,key));return json.loads(row[0])
    def contains(self,namespace,key):
        with self.lock:
            row=self.values.get((namespace,key))
            return bool(row and row[1]>=time.time())
    def discard(self,namespace,key):
        with self.lock:self._remove((namespace,key))
    def clear(self,namespace=None):
        with self.lock:
            for key in list(self.values):
                if namespace is None or key[0]==namespace:self._remove(key)
    def stats(self,namespace):
        with self.lock:
            rows=[v for k,v in self.values.items() if k[0]==namespace]
            return {'records':len(rows),'bytes':sum(v[2] for v in rows),'limit_bytes':self.namespace_bytes}
memory_cache=MemoryCache()
