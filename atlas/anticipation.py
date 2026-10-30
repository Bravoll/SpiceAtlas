"""Version-local resource packets and weighted depth-one prefetch (public resources only)."""
from __future__ import annotations
import asyncio,collections,hashlib,json,time,uuid
from .cache_memory import CACHE_MODE,memory_cache
from .storage import Store,now_iso
from .workspaces import workspaces
from .preferences import preferences
from .catalogue import catalogue
from .activity import activity
from .runtime import runtime,event

REMOTE_ACTIONS={'entry','form','source','imageProfile','provider','language','translate','refreshArticle','refreshImages'}
class Anticipation:
    def __init__(self,reader):
        self.reader=reader;self.store=reader.store;self.session=uuid.uuid4().hex;self.jobs={};self.generations=collections.defaultdict(int);self.pins={};self.failures={};self.cursors={}
    def connect(self):
        db=self.store.connect();db.executescript('''
        CREATE TABLE IF NOT EXISTS resource_packets(fingerprint TEXT PRIMARY KEY,kind TEXT,descriptor TEXT,cache_keys TEXT,hits INTEGER DEFAULT 0,last_used REAL);
        CREATE TABLE IF NOT EXISTS resource_seen(event_id TEXT,fingerprint TEXT,at REAL,PRIMARY KEY(event_id,fingerprint));
        CREATE TABLE IF NOT EXISTS operation_totals(kind TEXT PRIMARY KEY,n INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS operation_sessions(session TEXT,kind TEXT,n INTEGER NOT NULL,PRIMARY KEY(session,kind));
        CREATE TABLE IF NOT EXISTS operation_events(id TEXT PRIMARY KEY,session TEXT,kind TEXT,at REAL,context TEXT);
        CREATE INDEX IF NOT EXISTS operation_events_at ON operation_events(at DESC);
        ''');return db
    def sticky_ids(self):
        key=workspaces.current_id;old=self.pins.get(key)
        if old and time.monotonic()-old[0]<5:return old[1]
        first=[r['id'] for r in catalogue.page(scope='all',limit=30)['entries']]
        favorites=[row['entry_id'] for row in activity.collection('favorites')]
        ids=list(dict.fromkeys([*first,*favorites]));self.pins[key]=(time.monotonic(),ids);return ids
    def descriptor(self,value):
        if not isinstance(value,dict):raise ValueError('Choose a structured resource')
        kind=value.get('kind');key=str(value.get('entry',''))[:180];item=catalogue.get(key)
        if not item or kind not in {'article','images','pronunciation','other','translation','web_article'}:raise ValueError('Unknown online resource or local entry')
        if kind=='article':
            source=str(value.get('source','auto')).split(':')[0]
            if source not in {'auto','zhwiki','enwiki','bing','google','baidu','wikidata',*item.get('references',{})}:raise ValueError('Unknown article source')
            preferred='en' if value.get('preferred')=='en' else 'zh'
            variant='zh-hant' if str(value.get('variant','')).lower() in {'zh-hant','zh-tw','zh-hk'} else 'zh-hans'
            if source=='enwiki':preferred='en';variant='en'
            elif source=='zhwiki':preferred='zh'
            return {'kind':kind,'entry':key,'source':source,'preferred':preferred,'variant':variant}
        if kind=='web_article':
            from .source_registry import provider_for
            url=str(value.get('url',''))
            if len(url)>2000 or not provider_for(url):raise ValueError('Choose a reviewed public article URL')
            return {'kind':kind,'entry':key,'url':url}
        if kind=='translation':
            from .preferences import TRANSLATION_LANGUAGES
            p=preferences.values();provider=p['translation_provider'];target=value.get('target');source=str(value.get('source','')).split(':')[0];revision=str(value.get('revision') or '')[:80]
            if provider not in {'google','azure'} or not p[provider+'_translate_key'] or source not in {'zhwiki','enwiki'} or target not in TRANSLATION_LANGUAGES-{'auto'} or not revision:raise ValueError('Only configured cloud translations with a source revision are online packets')
            return {'kind':kind,'entry':key,'source':source,'target':target,'revision':revision,'provider':provider,'variant':'zh-hant' if str(value.get('variant','')).lower()=='zh-hant' else 'zh-hans'}
        if kind=='images':
            provider=value.get('provider','commons');form=value.get('form') or item['forms'][0]['id'];profile=value.get('profile') or 'auto'
            if provider not in {'commons','google','bing','baidu'} or form not in {x['id'] for x in item['forms']}:raise ValueError('Choose an API image provider and valid form')
            from .image_lexicon import lexicon
            if profile!='auto' and profile not in lexicon.summary()['profiles']:raise ValueError('Unknown image profile')
            return {'kind':kind,'entry':key,'provider':provider,'form':form,'profile':profile}
        return {'kind':kind,'entry':key}
    @staticmethod
    def fingerprint(desc):return hashlib.sha256(json.dumps(desc,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    def keys(self,desc):
        kind=desc['kind'];key=desc['entry'];item=catalogue.get(key)
        if kind=='web_article':return ['reference-article:v2:'+hashlib.sha256((key+desc['url']).encode()).hexdigest()]
        if kind=='article':
            if desc['source'] not in {'auto','enwiki','zhwiki'}:return ['source-article:v1:'+self.fingerprint(desc)]
            first='enwiki' if desc['preferred']=='en' else 'zhwiki'
            sources=[desc['source']] if desc['source']!='auto' else [first,'enwiki' if first=='zhwiki' else 'zhwiki']
            return [f"article:{key}:{source}:"+(desc['variant'] if source=='zhwiki' else 'en') for source in sources if item.get('wiki',{}).get(source)]
        if kind=='images':return [f"v4images:{key}:{desc['form']}:{desc['provider']}:{desc['profile']}"]
        if kind=='pronunciation':
            from .pronunciation import name_metadata
            word=name_metadata(item)['spoken_english'].lower()
            return ['pronunciation:v1:'+word] if word else []
        return [('translation-packet:v1:' if kind=='translation' else 'other-packet:v2:')+self.fingerprint(desc)]
    def observe(self,desc,event_id=''):
        keys=self.keys(desc)
        if not keys:return 0
        fingerprint=self.fingerprint(desc);event_id=str(event_id or uuid.uuid4().hex)[:100]
        with self.connect() as db:
            inserted=db.execute('INSERT OR IGNORE INTO resource_seen VALUES(?,?,?)',(event_id,fingerprint,time.time())).rowcount
            if inserted:
                db.execute('INSERT INTO resource_packets VALUES(?,?,?,?,1,?) ON CONFLICT(fingerprint) DO UPDATE SET hits=hits+1,last_used=excluded.last_used,cache_keys=excluded.cache_keys',(fingerprint,desc['kind'],json.dumps(desc,ensure_ascii=False),json.dumps(keys),time.time()))
            row=db.execute('SELECT hits FROM resource_packets WHERE fingerprint=?',(fingerprint,)).fetchone();hits=row[0] if row else 0
            db.execute('DELETE FROM resource_seen WHERE rowid IN (SELECT rowid FROM resource_seen ORDER BY at DESC LIMIT -1 OFFSET 3000)')
        reason='first_page_or_favorite' if desc['entry'] in self.sticky_ids() else 'frequent' if hits>=preferences.values()['cache_promote_hits'] else None
        if reason:
            for key in keys:self.store.retain(key,reason)
        return hits
    def lookup(self,value,event_id='',track=True,protected_only=False):
        desc=self.descriptor(value)
        if track:self.observe(desc,event_id)
        keys=self.keys(desc)
        # A cached secondary language must not mask an uncached mapped primary.
        if desc["kind"]=="article" and desc["source"]=="auto":keys=keys[:1]
        for key in keys:
            cached=self.store.get(key)
            if not cached or cached['stale'] or protected_only and cached.get('tier')=='disk':continue
            data=cached['value']
            if desc['kind'] in {'article','web_article'} and data.get('mode')!='article':continue
            if desc['kind']=='images' and not data.get('images'):continue
            if desc['kind']=='pronunciation' and not data.get('variants'):continue
            if desc['kind']=='other' and not data.get('cards'):continue
            if desc['kind']=='translation' and not data.get('blocks'):continue
            tier=cached.get('tier','disk');data={**data,'delivery':{'memory':'memory_cache','retained':'retained_cache'}.get(tier,'cache')}
            if desc['kind']=='images':data=self.reader.image_delivery(data)
            return {'hit':True,'tier':tier,'resource':desc,'value':data}
        return {'hit':False,'resource':desc}
    def record_operation(self,value):
        kind=value.get('kind');identifier=str(value.get('id',''))[:100]
        if kind not in REMOTE_ACTIONS or not identifier:raise ValueError('Only online-resource operations are counted')
        context=value.get('context') or {};context={k:v for k,v in context.items() if k in {'entry','form','source','profile','provider','variant','preferred'} and isinstance(v,str) and len(v)<=180}
        if not catalogue.get(context.get('entry','')):raise ValueError('Choose a local entry before tracking an online operation')
        with self.connect() as db:
            inserted=db.execute('INSERT OR IGNORE INTO operation_events VALUES(?,?,?,?,?)',(identifier,self.session,kind,time.time(),json.dumps(context,ensure_ascii=False))).rowcount
            if inserted:
                db.execute('INSERT INTO operation_totals VALUES(?,1) ON CONFLICT(kind) DO UPDATE SET n=n+1',(kind,))
                db.execute('INSERT INTO operation_sessions VALUES(?,?,1) ON CONFLICT(session,kind) DO UPDATE SET n=n+1',(self.session,kind))
                db.execute('DELETE FROM operation_events WHERE rowid IN (SELECT rowid FROM operation_events ORDER BY at DESC LIMIT -1 OFFSET 5000)')
        if inserted:workspaces.touch()
        self.cancel();return {'ok':True,'counted':bool(inserted)}
    def stats(self):
        with self.connect() as db:
            history=dict(db.execute('SELECT kind,n FROM operation_totals'));session=dict(db.execute('SELECT kind,n FROM operation_sessions WHERE session=?',(self.session,)))
            recent=dict(collections.Counter(row[0] for row in db.execute('SELECT kind FROM operation_events ORDER BY at DESC,rowid DESC LIMIT 30')))
            packets=[{'fingerprint':r[0],'kind':r[1],'resource':json.loads(r[2]),'hits':r[3],'last_used':r[4],'cache_keys':json.loads(r[5])} for r in db.execute('SELECT fingerprint,kind,descriptor,hits,last_used,cache_keys FROM resource_packets ORDER BY hits DESC,last_used DESC LIMIT 24')]
            retained=db.execute('SELECT COUNT(*) FROM retention r JOIN cache c ON c.key=r.key').fetchone()[0]
            keys=list({key for packet in packets for key in packet['cache_keys']})
            present={r[0]:('retained' if r[1] else 'disk') for r in db.execute('SELECT c.key,r.reason FROM cache c LEFT JOIN retention r ON r.key=c.key WHERE c.key IN ('+','.join('?' for _ in keys)+') AND (r.key IS NOT NULL OR c.expires>=?)',[*keys,time.time()])} if keys else {}
            for packet in packets:
                packet['tier']='memory' if any(memory_cache.contains(self.store.namespace,key) for key in packet['cache_keys']) else next((present[key] for key in packet['cache_keys'] if key in present),'not_cached')
                packet['cached']=packet['tier']!='not_cached'
                packet.pop('cache_keys')
        p=preferences.values();ramp=min(1,sum(session.values())/p['cache_session_threshold']);weights={'history':p['cache_weight_history']+(1-ramp)*(p['cache_weight_session']+p['cache_weight_recent']),'session':p['cache_weight_session']*ramp,'recent':p['cache_weight_recent']*ramp};denom=sum(weights.values()) or 1;weights={k:v/denom for k,v in weights.items()}
        tables={'history':history,'session':session,'recent':recent};rows=[]
        for kind in sorted(REMOTE_ACTIONS):
            counts={name:table.get(kind,0) for name,table in tables.items()};score=sum(weights[name]*counts[name]/max(1,sum(tables[name].values())) for name in tables)
            rows.append({'kind':kind,**counts,'score':round(score,6)})
        rows.sort(key=lambda row:(-row['score'],row['kind']))
        return {'session_id':self.session,'rows':rows,'history_total':sum(history.values()),'session_total':sum(session.values()),'recent_total':sum(recent.values()),'recent_window':30,'effective_weights':weights,'session_threshold':p['cache_session_threshold'],'promote_hits':p['cache_promote_hits'],'retained_resources':retained,'memory':memory_cache.stats(self.store.namespace),'packets':packets}
    def cancel(self):
        version=workspaces.current_id;self.generations[version]+=1
        for task in list(self.jobs.get(version,set())):task.cancel()
    def plan(self,context):
        p=preferences.values();version=workspaces.current_id
        if runtime.paused or not p['prefetch_enabled']:return {'jobs':[],'generation':self.generations[version]}
        jobs=[];seen=set();now=time.monotonic();scores={r['kind']:r['score'] for r in self.stats()['rows']}
        def add(raw,tier,score,action):
            try:desc=self.descriptor(raw)
            except ValueError:return
            fingerprint=self.fingerprint(desc)
            if fingerprint in seen or self.failures.get((version,fingerprint),0)>now:return
            seen.add(fingerprint)
            if self.lookup(desc,track=False)['hit']:return
            jobs.append({'resource':desc,'tier':tier,'score':round(score,6),'action':action,'fingerprint':fingerprint})
        preferred=context.get('preferred','en');variant=context.get('variant','zh-hans')
        # Warm all protected entries in small rotating batches, without an unbounded task queue.
        pins=self.sticky_ids();cursor=self.cursors.get(version,0)%max(1,len(pins));batch=(pins[cursor:]+pins[:cursor])[:12];self.cursors[version]=(cursor+12)%max(1,len(pins))
        for i,key in enumerate(batch):
            item=catalogue.get(key)
            if not item:continue
            source=next((s for s in (('enwiki','zhwiki') if preferred=='en' else ('zhwiki','enwiki')) if item.get('wiki',{}).get(s)),None)
            if source:add({'kind':'article','entry':key,'source':source,'preferred':preferred,'variant':variant},'longterm',2-i*.001,'first_page_or_favorite')
            add({'kind':'images','entry':key},'longterm',1.9-i*.001,'first_page_or_favorite')
            if self.keys({'kind':'pronunciation','entry':key}):add({'kind':'pronunciation','entry':key},'longterm',1.8-i*.001,'first_page_or_favorite')
        item=catalogue.get(context.get('entry',''))
        if item:
            key=item['id'];form=context.get('form') or item['forms'][0]['id'];profile=context.get('profile','auto')
            for url in context.get('visible_sources',[])[:10]:add({'kind':'web_article','entry':key,'url':url},'memory',scores.get('source',0),'source')
            for row in item['forms']:
                if row['id']!=form:add({'kind':'images','entry':key,'form':row['id'],'profile':profile},'memory',scores.get('form',0),'form')
            from .image_lexicon import lexicon
            for image_profile in lexicon.summary()['profiles']:
                if image_profile!=profile:add({'kind':'images','entry':key,'form':form,'profile':image_profile},'memory',scores.get('imageProfile',0),'imageProfile')
            if context.get('source')!='other':add({'kind':'other','entry':key},'memory',scores.get('source',0),'source')
            text_score=max(scores.get('source',0),scores.get('language',0),scores.get('refreshArticle',0))
            for source in ('zhwiki','enwiki'):
                if item.get('wiki',{}).get(source):
                    add({'kind':'article','entry':key,'source':source,'preferred':preferred,'variant':variant},'memory',text_score,'source')
                    if source=='zhwiki' and scores.get('language',0):add({'kind':'article','entry':key,'source':source,'preferred':'zh','variant':'zh-hans' if variant.lower()=='zh-hant' else 'zh-hant'},'memory',scores['language'],'language')
            add({'kind':'images','entry':key,'form':form,'profile':profile},'memory',max(scores.get('provider',0),scores.get('refreshImages',0)),'provider')
            # The visible next-entry actions are one edge away; related records are not expanded recursively.
            for key in list(dict.fromkeys(context.get('visible_entries',[])[:30]+[r['id'] for r in catalogue.related(item)[:8]]))[:12]:
                neighbor=catalogue.get(key)
                if not neighbor or key==item['id']:continue
                source=next((s for s in ('enwiki','zhwiki') if neighbor.get('wiki',{}).get(s)),None)
                if source:add({'kind':'article','entry':key,'source':source,'preferred':preferred,'variant':variant},'memory',scores.get('entry',0),'entry')
                add({'kind':'images','entry':key},'memory',scores.get('entry',0),'entry')
        jobs=[job for job in jobs if job['tier']=='longterm' or job['score']>0]
        jobs.sort(key=lambda row:-row['score'])
        return {'jobs':jobs[:48],'generation':self.generations[version],'depth':1,'prediction_only_memory':True}
    async def fetch(self,raw,tier,generation):
        version=workspaces.current_id;desc=self.descriptor(raw);fingerprint=self.fingerprint(desc)
        if generation!=self.generations[version] or runtime.paused:raise ValueError('Prefetch context changed')
        if tier not in {'memory','longterm'}:raise ValueError('Choose memory or longterm')
        if tier=='longterm' and desc['entry'] not in self.sticky_ids():raise ValueError('Only protected entries use idle long-term warming')
        async def run():
            token=CACHE_MODE.set(tier)
            try:
                async with asyncio.timeout(min(30,preferences.values()['other_total_timeout']) if desc['kind']=='other' else 12):
                    if desc['kind']=='article':
                        from .providers import ARTICLE_VARIANT
                        variant=ARTICLE_VARIANT.set(desc['variant'])
                        try:value=await self.reader.article(desc['entry'],desc['source'],False,desc['preferred'])
                        finally:ARTICLE_VARIANT.reset(variant)
                    elif desc['kind']=='web_article':
                        from .web_sources import read_reference
                        from .source_registry import provider_for
                        value=await read_reference(catalogue.get(desc['entry']),provider_for(desc['url'])['id'],desc['url'],self.store)
                    elif desc['kind']=='images':value=await self.reader.images(desc['entry'],desc['provider'],desc['form'],False,desc['profile'])
                    elif desc['kind']=='pronunciation':
                        from .pronunciation import pronunciations
                        value=await pronunciations.for_entry(catalogue.get(desc['entry']))
                    else:
                        from .other_sources import stream_cards
                        from .health import health
                        cards=[]
                        async for record in stream_cards(catalogue.get(desc['entry']),preferences.values(),health.report()):
                            if record['type']=='card':cards.append(record['card'])
                        if cards:self.store.put(self.keys(desc)[0],{'cards':cards,'fetched_at':now_iso(),'mode':'collection'},900)
                    event('cache.warm',entry=desc['entry'],kind=desc['kind'],tier=tier)
                    ok=bool(self.lookup(desc,track=False)['hit'])
                    if not ok:self.failures[(version,fingerprint)]=time.monotonic()+600
                    return {'ok':ok,'resource':desc}
            except asyncio.CancelledError:raise
            except Exception as exc:
                self.failures[(version,fingerprint)]=time.monotonic()+600
                return {'ok':False,'resource':desc,'reason':getattr(exc,'code','unavailable'),'browser_fallback':desc['kind'] in {'article','images'}}
            finally:CACHE_MODE.reset(token)
        task=asyncio.create_task(run());self.jobs.setdefault(version,set()).add(task)
        try:return await task
        finally:self.jobs.get(version,set()).discard(task)
