"""Two-second diagnostic rounds. Publish once; reject all late browser results."""
from __future__ import annotations
import asyncio,copy,time,uuid
from urllib.parse import urlsplit
import httpx
from .activity import activity
from .workspaces import workspaces
from .preferences import preferences
from .storage import now_iso
from .network import client_options
from .translations import cloud_translate
from .runtime import runtime,event
BROWSER_PROBES=[
 {'id':'zhwiki','url':'https://zh.wikipedia.org/w/api.php','params':{'action':'parse','page':'歐芹','redirects':1,'prop':'revid','format':'json','origin':'*'}},
 {'id':'enwiki','url':'https://en.wikipedia.org/w/api.php','params':{'action':'parse','page':'Parsley','redirects':1,'prop':'revid','format':'json','origin':'*'}},
 {'id':'commons','url':'https://commons.wikimedia.org/w/api.php','params':{'action':'query','list':'search','srnamespace':6,'srsearch':'parsley filetype:bitmap','srlimit':1,'format':'json','origin':'*'}},
]
class Health:
 interval=600
 def __init__(self,budget_ms=2000):
  self.budget_ms=budget_ms;self.reports={};self.tasks={};self.browser={};self.rounds={};self.next_due={};self.activated=set();self.loop_task=None;self.wakeup=None
 def report(self):
  key=workspaces.current_id
  value=copy.deepcopy(self.reports.get(key,{'phase':'checking','revision':0,'services':{},'completed_rounds':0,'initial':True}))
  current=self.rounds.get(key);active=bool(current and current['active'])
  value.update(interval_seconds=self.interval,sample='欧芹 / Parsley',budget_ms=self.budget_ms,paused=runtime.paused,needs_retest=runtime.needs_retest)
  if runtime.needs_retest:value['phase']='awaiting_retest'
  if current:
   value.update(round_id=current['id'],remaining_ms=max(0,int((current['deadline']-time.monotonic())*1000)) if active else 0)
  else:value.update(round_id=None,remaining_ms=0)
  if active:value['phase']='checking'
  value['next_check_in_ms']=max(0,int((self.next_due.get(key,time.monotonic())-time.monotonic())*1000))
  return value
 def publish(self,rows,browser_rows=None,round_id=None):
  key=workspaces.current_id;previous=self.reports.get(key);services={};changed=[]
  others=[row for row in rows if row['id'].startswith('other_') and row['id']!='other_sources']
  if others:
   aggregate=True if any(row.get('ok') is True for row in others) else False if all(row.get('ok') is False for row in others) else None
   rows=[*[row for row in rows if row['id']!='other_sources'],{'id':'other_sources','kind':'function','ok':aggregate,'message':'Availability of reviewed knowledge providers; a timeout is inconclusive'}]
  for item in rows:
   row=dict(item);service=row['id'];row.setdefault('backend_ok',row.get('ok'))
   browser=(browser_rows or {}).get(service)
   if browser is not None:row.update(browser_ok=browser['ok'],browser_checked_at=browser['checked_at'])
   else:row.pop('browser_ok',None);row.pop('browser_checked_at',None)
   paths=[row['backend_ok']]
   if service in {'zhwiki','enwiki','commons'}:paths.append(row.get('browser_ok'))
   resolved=True if True in paths else False if all(value is False for value in paths) else None
   old=(previous or {}).get('services',{}).get(service)
   row['status']='available' if resolved is True else 'unavailable' if resolved is False else 'unconfirmed'
   row['ok']=resolved if resolved is not None else (old or {}).get('ok')
   services[service]=row
   if resolved is False and (not old or old.get('ok') is not False) or resolved is True and old and old.get('ok') is False:changed.append({'service':service,'before':old.get('ok') if old else None,'now':resolved,'http_status':row.get('http_status'),'message':row.get('message','')})
  revision=(previous or {}).get('revision',0)+(1 if changed or not previous else 0)
  report={'phase':'ready','checked_at':now_iso(),'revision':revision,'services':services,'completed_rounds':(previous or {}).get('completed_rounds',0)+1,'initial':False,'round_id':round_id,'interval_seconds':self.interval,'sample':'欧芹 / Parsley','budget_ms':self.budget_ms}
  self.reports[key]=report
  if changed:activity.notify('来源可用性变化 / Source availability changed',{'revision':revision,'changes':changed});activity.log('services.change',{'revision':revision,'changes':changed})
  event('health.round.finished',round_id=round_id,services=len(services),available=sum(v['ok'] is True for v in services.values()),changes=len(changed),budget_ms=self.budget_ms)
  return self.report()
 def browser_results(self,rows,round_id=None):
  key=workspaces.current_id;current=self.rounds.get(key)
  if not current or not current['active'] or round_id!=current['id'] or time.monotonic()>=current['deadline']:
   return {**self.report(),'browser_results_ignored':True}
  for row in rows:
   if row.get('id') in {'zhwiki','enwiki','commons'} and isinstance(row.get('ok'),bool):
    value={'ok':row['ok'],'checked_at':now_iso()};current['browser'][row['id']]=value;self.browser[(key,row['id'])]=value
  return self.report()
 def browser_plan(self):
  report=self.report();active=report.get('phase')=='checking' and report.get('remaining_ms',0)>0 and not runtime.paused
  return {**report,'probes':BROWSER_PROBES if active else []}
 def begin_for_browser(self):
  key=workspaces.current_id;self.activated.add(key)
  if runtime.needs_retest:return self.browser_plan()
  if not runtime.paused and (key not in self.rounds or time.monotonic()>=self.next_due.get(key,0)):self.restart()
  if self.wakeup:self.wakeup.set()
  return self.browser_plan()
 def specs(self):
  p=preferences.values();rows=[{**x,'kind':'api'} for x in BROWSER_PROBES]
  rows.extend([
   {'id':'pronunciation_dictionary','url':'https://api.dictionaryapi.dev/api/v2/entries/en/parsley','kind':'api','dictionary':True},
   {'id':'wikidata','url':'https://www.wikidata.org/w/api.php','params':{'action':'wbsearchentities','search':'parsley','language':'en','limit':1,'format':'json'},'kind':'api'},
   {'id':'gbif','url':'https://api.gbif.org/v1/species/match','params':{'name':'Petroselinum crispum'},'kind':'api'},
   {'id':'commons_web','url':'https://commons.wikimedia.org/wiki/Category:Petroselinum_crispum','kind':'web'},
   {'id':'wikidata_web','url':'https://www.wikidata.org/wiki/Q25284','kind':'web'},
   {'id':'gbif_web','url':'https://www.gbif.org/species/7828157','kind':'web'},
   {'id':'zhwiki_web','url':'https://zh.wikipedia.org/wiki/歐芹','kind':'web'},
   {'id':'enwiki_web','url':'https://en.wikipedia.org/wiki/Parsley','kind':'web'},
   {'id':'bing','url':'https://www.bing.com/search?q=parsley&mkt=en-AU','kind':'web'},
   {'id':'bing_cn','url':'https://cn.bing.com/search?q=%E6%AC%A7%E8%8A%B9&mkt=zh-CN','kind':'web'},
   {'id':'google','url':'https://www.google.com/search?q=parsley&hl=en','kind':'web'},
   {'id':'baidu','url':'https://baike.baidu.com/item/%E6%AC%A7%E8%8A%B9','kind':'web'},
   {'id':'baidu_images','url':'https://image.baidu.com/search/index?tn=baiduimage&word=parsley','kind':'web'},
  ])
  from .catalogue import catalogue
  entry=catalogue.get('parsley') or {}
  for key,ref in entry.get('references',{}).items():
   if key not in {x['id'] for x in rows}:rows.append({'id':key,'url':ref['url'],'kind':'web'})
  import json
  from .storage import ROOT
  for record in json.loads((ROOT/'data/catalog.json').read_text('utf-8'))['entries']:
   for key,ref in record.get('references',{}).items():
    if key not in {x['id'] for x in rows}:rows.append({'id':key,'url':ref['url'],'kind':'web','tested_entry':record['id'],'sample_note':'Representative known page; Parsley mapping not available'})
  if p['lm_enabled']:rows.append({'id':'translation_local','url':p['lm_base_url'].rstrip('/')+'/models','kind':'function','local':True})
  if p['google_translate_key']:rows.append({'id':'translation_google','url':'https://translation.googleapis.com','kind':'function','cloud':'google'})
  if p['azure_translate_key']:rows.append({'id':'translation_azure','url':'https://api.cognitive.microsofttranslator.com','kind':'function','cloud':'azure'})
  if p['google_api_key'] and p['google_cse_id']:rows.append({'id':'google_images','url':'https://customsearch.googleapis.com/customsearch/v1','params':{'key':p['google_api_key'],'cx':p['google_cse_id'],'q':'parsley','searchType':'image','num':1},'kind':'api'})
  from .source_registry import registry
  for profile in registry()['providers']:
   url=profile.get('sample_url')
   if profile['id']=='gbif':url='https://api.gbif.org/v1/species/match?name=Petroselinum%20crispum'
   elif profile['id']=='wikispecies':url='https://species.wikimedia.org/w/api.php?action=parse&page=Petroselinum_crispum&prop=revid&format=json'
   elif profile['id']=='wikibooks':url='https://en.wikibooks.org/w/api.php?action=parse&page=Cookbook:Parsley&prop=revid&format=json'
   if url:rows.append({'id':'other_'+profile['id'],'url':url,'kind':'api' if profile['id'] in {'gbif','wikispecies','wikibooks'} else 'web','tested_entry':'sampled_reference','sample_note':'Known public provider page; not a culinary-use verification'})
  return rows
 async def probe(self,spec,gate):
  result={'id':spec['id'],'kind':spec['kind'],'host':urlsplit(spec['url']).hostname,'url':spec['url'],'checked_at':now_iso(),'tested_entry':spec.get('tested_entry','parsley')}
  try:
   async with gate:
    if spec.get('cloud'):
     await cloud_translate(spec['cloud'],['Parsley'],'zh-Hans',preferences.values());return {**result,'ok':True,'http_status':200}
    options=client_options(9);options['follow_redirects']=True;options['max_redirects']=4
    if spec.get('local'):
     options.pop('proxy',None);options['trust_env']=False
     key=preferences.values()['lm_api_key']
     if key:options['headers']['Authorization']='Bearer '+key
    async with httpx.AsyncClient(**options) as client:response=await client.get(spec['url'],params=spec.get('params'))
   result['http_status']=response.status_code
   if response.status_code!=200:return {**result,'ok':False,'message':'HTTP '+str(response.status_code)}
   if spec['kind'] in {'api','function'}:
    data=response.json()
    if spec.get('dictionary'):
     if not isinstance(data,list) or not data or not data[0].get('word'):return {**result,'ok':False,'message':'Invalid dictionary response'}
    elif not isinstance(data,dict) or data.get('error'):return {**result,'ok':False,'message':'API error or invalid JSON'}
    if spec.get('local') and not data.get('data'):return {**result,'ok':False,'message':'No loaded model'}
   else:
    text=response.text[:30000].lower();url=str(response.url).lower()
    challenge=any(x in url for x in ('/sorry/','/consent','/captcha','wappass.baidu')) or '<title>just a moment' in text or 'enable javascript and cookies to continue' in text
    if challenge:return {**result,'ok':False,'message':'Verification or consent page'}
    result['frame_restricted']=response.headers.get('x-frame-options','').upper() in {'DENY','SAMEORIGIN'} or 'frame-ancestors' in response.headers.get('content-security-policy','').lower()
   return {**result,'ok':True}
  except httpx.TimeoutException:return {**result,'ok':None,'message':'Connection test timed out; availability is unconfirmed'}
  except (httpx.HTTPError,ValueError,KeyError,ImportError):return {**result,'ok':False,'message':'Connection or API response failed'}
 async def _run(self,current):
  key=current['key'];tasks=[]
  try:
   with workspaces.use(key):
    gate=asyncio.Semaphore(64)
    specs=self.specs();tasks=[asyncio.create_task(self.probe(spec,gate)) for spec in specs]
    if tasks:await asyncio.wait(tasks,timeout=max(0,current['deadline']-time.monotonic()))
    await asyncio.sleep(max(0,current['deadline']-time.monotonic()))
    if not current['active']:return self.report()
    rows=[]
    for spec,task in zip(specs,tasks):
     if task.done() and not task.cancelled():
      try:rows.append(task.result());continue
      except Exception:pass
     task.cancel()
     task.add_done_callback(lambda t:None if t.cancelled() else t.exception())
     rows.append({'id':spec['id'],'kind':spec['kind'],'ok':None,'backend_ok':None,'host':urlsplit(spec['url']).hostname,'code':'round_timeout','message':f'No completed result within {self.budget_ms} ms'})
    current['active']=False
    return self.publish(rows,current['browser'],current['id'])
  finally:
   current['active']=False
   for task in tasks:
    if not task.done():task.cancel()
 async def check(self):
  self.restart(force=True)
  return await self.tasks[workspaces.current_id]
 def restart(self,force=False):
  key=workspaces.current_id;current=self.rounds.get(key)
  if runtime.paused or runtime.needs_retest and not force:return self.report()
  if current and current['active'] and not force:return self.report()
  if current:current['active']=False
  old=self.tasks.get(key)
  if old and not old.done():old.cancel()
  start=time.monotonic();current={'id':uuid.uuid4().hex,'key':key,'start':start,'deadline':start+self.budget_ms/1000,'browser':{},'active':True}
  self.rounds[key]=current;self.next_due[key]=current['deadline']+self.interval
  self.tasks[key]=asyncio.create_task(self._run(current))
  event('health.round.started',round_id=current['id'],budget_ms=self.budget_ms)
  return self.report()
 async def loop(self):
  while True:
   self.wakeup.clear();key=workspaces.active_id;wait=self.interval
   with workspaces.use(key):
    if key in self.activated and not runtime.paused and not runtime.needs_retest:
     due=self.next_due.get(key,0)
     if time.monotonic()>=due:self.restart()
     wait=max(.05,self.next_due.get(key,time.monotonic()+self.interval)-time.monotonic())
   try:await asyncio.wait_for(self.wakeup.wait(),timeout=min(wait,self.interval))
   except asyncio.TimeoutError:pass
 def start(self):
  self.wakeup=asyncio.Event();self.loop_task=asyncio.create_task(self.loop())
 def switched(self):
  if self.wakeup:self.wakeup.set()
 async def suspend(self):
  for current in self.rounds.values():current['active']=False
  for task in self.tasks.values():task.cancel()
  await asyncio.gather(*self.tasks.values(),return_exceptions=True)
  self.tasks.clear()
 def resume(self):
  for key in self.activated:self.next_due[key]=time.monotonic()+self.interval
  self.switched()
 async def stop(self):
  current_loop=asyncio.get_running_loop()
  all_tasks=[task for task in list(self.tasks.values())+([self.loop_task] if self.loop_task else []) if task.get_loop() is current_loop]
  for current in self.rounds.values():current['active']=False
  for task in all_tasks:task.cancel()
  await asyncio.gather(*all_tasks,return_exceptions=True);self.tasks.clear();self.loop_task=None;self.wakeup=None
health=Health()
