"""Process-wide soft pause and redacted terminal events (no request bodies)."""
from __future__ import annotations
import json
import logging
import re
import threading
import asyncio
import uuid
from datetime import datetime, timezone

SENSITIVE=re.compile(r'key|token|secret|password|authorization|credential',re.I)

def scrub(value):
    if isinstance(value,dict):
        return {k:('[redacted]' if SENSITIVE.search(str(k)) else scrub(v)) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [scrub(x) for x in value[:100]]
    if isinstance(value,str):
        value=re.sub(r'(https?://)[^\s/@]+(?::[^\s/@]*)?@',r'\1[redacted]@',value)
        value=re.sub(r'(?i)(bearer\s+)[a-z0-9._~+/-]+',r'\1[redacted]',value)
        value=re.sub(r'(?i)((?:[?&]|\b)(?:api[_-]?key|key|token|secret|password)=)[^&\s]+',r'\1[redacted]',value)
        return value[:2000]
    return value

LOGGER=logging.getLogger('spice_atlas.runtime')
if not LOGGER.handlers:
    handler=logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    LOGGER.addHandler(handler)
LOGGER.setLevel(logging.INFO)
LOGGER.propagate=False

def event(event_name,**details):
    LOGGER.info('%s %s',event_name,json.dumps(scrub(details),ensure_ascii=False,separators=(',',':')))

class Runtime:
    def __init__(self):
        self.paused=False
        self.changed_at=None
        self.paused_jobs=[]
        self.phase='running'
        self.needs_retest=False
        self.listeners={}
        self.lock=threading.RLock()

    def set_paused(self,value):
        with self.lock:
            changed=self.paused!=bool(value)
            self.paused=bool(value)
            if changed:self.changed_at=datetime.now(timezone.utc).isoformat(timespec='seconds')
        if changed:event('service.pause' if value else 'service.resume')
        return self.public()

    def public(self):return {'paused':self.paused,'phase':self.phase,'needs_retest':self.needs_retest,'pause_changed_at':self.changed_at}

    def subscribe(self):
        key=uuid.uuid4().hex;queue=asyncio.Queue(maxsize=32)
        self.listeners[key]=(asyncio.get_running_loop(),queue)
        return key,queue

    def announce(self,kind,**data):
        payload={'kind':kind,**self.public(),**data}
        for loop,queue in list(self.listeners.values()):
            def send(queue=queue):
                if queue.full():queue.get_nowait()
                queue.put_nowait(payload)
            if not loop.is_closed():loop.call_soon_threadsafe(send)
        event(kind,phase=self.phase,needs_retest=self.needs_retest)
        return payload

runtime=Runtime()
